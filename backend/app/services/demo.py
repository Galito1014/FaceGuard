"""Datos de demostración: registros ficticios y eventos simulados.

Todo lo que se crea aquí lleva `is_simulated = 1` y la interfaz lo marca con
la etiqueta SIMULADO para que nunca se confunda con detecciones reales. Los
registros ficticios no tienen plantilla biométrica, por lo que nunca pueden
coincidir con una persona real frente a la cámara.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from app.config import config
from app.core.crypto import save_encrypted_file, secure_delete
from app.core.database import get_db, query, utcnow
from app.services.events import new_uid

FICTIONAL = [
    ("Persona Ficticia A-01", "alto", "Orden de restricción vigente respecto al condominio (caso de prueba)"),
    ("Persona Ficticia B-02", "medio", "Prohibición de ingreso por daños a áreas comunes (caso de prueba)"),
    ("Persona Ficticia C-03", "bajo", "Exempleado de mantenimiento sin autorización vigente (caso de prueba)"),
    ("Persona Ficticia D-04", "medio", "Incidente documentado con el personal de seguridad (caso de prueba)"),
    ("Persona Ficticia E-05", "alto", "Orden judicial de alejamiento solicitada por residente (caso de prueba)"),
    ("Persona Ficticia F-06", "bajo", "Reiteradas visitas no autorizadas (caso de prueba)"),
]


def _avatar(label: str, seed: int) -> bytes:
    """Avatar abstracto generado (no es una fotografía de una persona)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((320, 320, 3), np.uint8)
    base = rng.integers(40, 120, 3).tolist()
    img[:] = base
    cv2.circle(img, (160, 130), 70, [min(255, c + 60) for c in base], -1)
    cv2.ellipse(img, (160, 330), (120, 110), 0, 180, 360, [min(255, c + 40) for c in base], -1)
    cv2.rectangle(img, (0, 0), (320, 34), (0, 0, 0), -1)
    cv2.putText(img, "FICTICIO - DEMO", (70, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(img, label, (110, 145), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return jpg.tobytes()


def seed(user: dict, days: int = 7) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    created = []
    with get_db() as db:
        for i, (name, level, reason) in enumerate(FICTIONAL):
            uid = f"SIM-{random.randint(1000, 9999)}"
            photo = save_encrypted_file("photos", _avatar(name.split()[-1], i + 7))
            reg = (now - timedelta(days=random.randint(10, 120))).replace(microsecond=0)
            exp = (now + timedelta(days=random.choice([-3, 30, 90, 180, 365]))).replace(microsecond=0)
            status = "activo" if exp > now else "vencido"
            cur = db.execute(
                """INSERT INTO blacklist (uid, full_name, info, reason, legal_basis, alert_level, registered_at, expires_at,
                     status, notes, photo_file, embedding_enc, photo_quality, created_by, updated_at, is_simulated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,1)""",
                (uid, name, "Registro ficticio para demostración", reason,
                 "Documento de autorización ficticio N.º DEMO-" + str(100 + i), level, reg.isoformat(), exp.isoformat(),
                 status, "Dato simulado — no corresponde a una persona real", photo,
                 json.dumps({"ok": True, "simulated": True}), user["id"], utcnow()))
            db.execute("INSERT INTO blacklist_history (entry_id, user_id, username, action, changes, at) VALUES (?,?,?,?,?,?)",
                       (cur.lastrowid, user["id"], user["username"], "creado (demo)", "{}", utcnow()))
            created.append((cur.lastrowid, uid, name, level))

        # Historial simulado para gráficas (últimos `days` días).
        n_events = 0
        statuses = ["confirmada", "falso_positivo", "cerrada", "falso_positivo", "pendiente"]
        for d in range(days):
            day = now - timedelta(days=d)
            for _ in range(random.randint(12, 30)):
                t = day.replace(hour=random.choice([6, 7, 8, 8, 9, 12, 13, 17, 18, 18, 19, 20, 22]),
                                minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)
                if t > now:
                    continue
                db.execute(
                    """INSERT INTO events (uid, occurred_at, camera, type, faces_count, score, message, is_simulated)
                       VALUES (?,?,?,?,?,?,?,1)""",
                    (new_uid("EV"), t.isoformat(), config.camera_name, "deteccion", random.randint(1, 3),
                     round(random.uniform(0.1, 0.33), 3), "[SIMULADO] Rostro(s) detectado(s) sin coincidencia"))
                n_events += 1
            for _ in range(random.randint(0, 3)):
                eid, uid, name, level = random.choice(created)
                t = day.replace(hour=random.randint(6, 22), minute=random.randint(0, 59), microsecond=0)
                if t > now:
                    continue
                st = random.choice(statuses) if d > 0 else "pendiente"
                db.execute(
                    """INSERT INTO events (uid, occurred_at, camera, type, entry_id, entry_name, score, level, faces_count,
                         review_status, reviewer_name, reviewed_at, message, is_simulated)
                       VALUES (?,?,?,?,?,?,?,?,1,?,?,?,?,1)""",
                    (new_uid("EV"), t.isoformat(), config.camera_name, "coincidencia", eid, name,
                     round(random.uniform(0.45, 0.8), 3), level, st,
                     None if st == "pendiente" else user["username"],
                     None if st == "pendiente" else (t + timedelta(minutes=5)).isoformat(),
                     f"[SIMULADO] Posible coincidencia con {uid}"))
                n_events += 1
    return {"blacklist": len(created), "events": n_events}


def clear() -> dict[str, int]:
    files = [r["photo_file"] for r in query("SELECT photo_file FROM blacklist WHERE is_simulated = 1")]
    files += [r["snapshot_file"] for r in query("SELECT snapshot_file FROM events WHERE is_simulated = 1")]
    with get_db() as db:
        ev = db.execute("DELETE FROM events WHERE is_simulated = 1").rowcount
        bl = db.execute("DELETE FROM blacklist WHERE is_simulated = 1").rowcount
    for f in files:
        secure_delete(f)
    return {"blacklist": bl, "events": ev}
