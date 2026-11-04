"""Operaciones sobre personas y muestras faciales.

Las muestras viven en `face_samples`: una foto cifrada, su plantilla cifrada y
la versión del modelo que la generó. Los archivos se escriben antes que la fila
de la base de datos, y se borran si la fila no llega a guardarse.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

import numpy as np

from app.core.crypto import decrypt_embedding, encrypt_embedding, save_encrypted_file, secure_delete
from app.core.database import query, utcnow
from app.services.face_engine import MODEL_VERSION

log = logging.getLogger("faceguard.persons")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_similar(vec: np.ndarray, threshold: float, exclude_person: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Personas con una muestra parecida, incluidas las inactivas o vencidas.

    Lee y descifra las plantillas en cada llamada: solo se usa al registrar una
    fotografía, nunca en el procesamiento de video.
    """
    rows = query(
        """SELECT p.id, p.uid, p.full_name, p.classification, p.status, s.embedding_enc
           FROM face_samples s JOIN persons p ON p.id = s.person_id
           WHERE s.embedding_enc IS NOT NULL AND s.model_version = ?""", (MODEL_VERSION,))
    best: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r["id"] == exclude_person:
            continue
        try:
            sim = float(decrypt_embedding(r["embedding_enc"]) @ vec)
        except Exception:
            log.warning("Plantilla ilegible para %s", r["uid"])
            continue
        if sim >= threshold and sim > best.get(r["id"], {}).get("score", -1.0):
            best[r["id"]] = {"entry_id": r["id"], "uid": r["uid"], "full_name": r["full_name"],
                             "classification": r["classification"], "status": r["status"], "score": round(sim, 3)}
    return sorted(best.values(), key=lambda m: m["score"], reverse=True)[:limit]


def insert_sample(db: sqlite3.Connection, person_id: int, data: bytes, report: dict[str, Any], user_id: int | None,
                  primary: bool) -> tuple[int, str]:
    """Guarda la foto cifrada y su fila. Devuelve (id de la muestra, archivo)."""
    photo_file = save_encrypted_file("photos", data)
    try:
        cur = db.execute(
            """INSERT INTO face_samples (person_id, photo_file, embedding_enc, model_version, quality, content_hash,
                                         is_primary, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (person_id, photo_file, encrypt_embedding(report["embedding"]), MODEL_VERSION,
             json.dumps(report.get("metrics", {})), content_hash(data), int(primary), user_id, utcnow()))
    except Exception:
        secure_delete(photo_file)
        raise
    return cur.lastrowid, photo_file


def primary_photo_file(person_id: int) -> str | None:
    rows = query("SELECT photo_file FROM face_samples WHERE person_id = ? ORDER BY is_primary DESC, id LIMIT 1", (person_id,))
    return rows[0]["photo_file"] if rows else None
