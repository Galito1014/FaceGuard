"""Personas registradas: blacklist, personas autorizadas y sus muestras faciales."""
from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.api.common import norm_dt, paginate
from app.core.audit import audit
from app.core.crypto import read_encrypted_file, secure_delete
from app.core.database import get_db, query, query_one, utcnow
from app.core.security import client_ip, has_perm, require
from app.services.face_engine import engine, gallery
from app.services.persons import content_hash, find_similar, insert_sample, primary_photo_file
from app.services.settings_store import settings

router = APIRouter(prefix="/api/persons", tags=["persons"])

MAX_PHOTO_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 40_000_000  # evita agotar la memoria con una imagen muy comprimida
LEVELS = {"bajo", "medio", "alto"}
STATUSES = {"activo", "inactivo", "vencido"}
CLASSIFICATIONS = {"autorizada", "no_autorizada"}
AUTHORIZED_REASON = "Persona autorizada"
QUALITY_MESSAGE = "La fotografía no cumple los requisitos de calidad."

PERSON_SELECT = """
SELECT p.*,
       (SELECT COUNT(*) FROM face_samples s WHERE s.person_id = p.id) AS sample_count,
       (SELECT COUNT(*) FROM face_samples s WHERE s.person_id = p.id AND s.embedding_enc IS NOT NULL) AS template_count,
       (SELECT quality FROM face_samples s WHERE s.person_id = p.id ORDER BY s.is_primary DESC, s.id LIMIT 1) AS photo_quality
FROM persons p"""


def _serialize(row: dict, user: dict) -> dict:
    out = dict(row)
    out["has_photo"] = row["sample_count"] > 0
    out["has_template"] = row["template_count"] > 0
    out["is_simulated"] = bool(row["is_simulated"])
    out["photo_quality"] = json.loads(row["photo_quality"]) if row.get("photo_quality") else None
    out["can_view_photo"] = has_perm(user, "blacklist.photos")
    return out


def _person(person_id: int) -> dict:
    row = query_one(f"{PERSON_SELECT} WHERE p.id = ?", (person_id,))
    if not row:
        raise HTTPException(404, "Registro no encontrado.")
    return row


def image_pixels(data: bytes) -> int | None:
    """Píxeles según la cabecera, sin descomprimir la imagen."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big") * int.from_bytes(data[20:24], "big")
    i = 2
    while i + 9 < len(data) and data[i] == 0xFF:  # segmentos JPEG hasta el marcador SOF
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 5:i + 7], "big") * int.from_bytes(data[i + 7:i + 9], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


async def read_photo(photo: UploadFile) -> bytes:
    data = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "La fotografía supera 6 MB.")
    if not data[:3] == b"\xff\xd8\xff" and not data[:8] == b"\x89PNG\r\n\x1a\n":
        raise HTTPException(415, "Formato no admitido. Use JPG o PNG.")
    if (image_pixels(data) or 0) > MAX_PIXELS:
        raise HTTPException(413, "La imagen tiene demasiados píxeles. Redúzcala antes de subirla.")
    return data


def _public_report(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "embedding"}


def _validated_report(data: bytes) -> dict:
    report = engine.analyze_photo(data)
    if not report["ok"]:
        raise HTTPException(422, {"message": QUALITY_MESSAGE, "report": _public_report(report)})
    return report


def _check_duplicates(report: dict, confirmed: bool, exclude: int | None = None) -> None:
    """Un posible duplicado no se registra sin una decisión del administrador."""
    if confirmed:
        return
    matches = find_similar(report["embedding"], settings.get("match_threshold"), exclude)
    if matches:
        raise HTTPException(409, {"message": "La fotografía se parece a una persona ya registrada.", "duplicates": matches})


def _validate_fields(fields: dict) -> dict:
    for key in ("full_name", "reason", "legal_basis"):
        if key in fields and not str(fields[key]).strip():
            raise HTTPException(422, f"El campo '{key}' es obligatorio.")
    if "alert_level" in fields and fields["alert_level"] not in LEVELS:
        raise HTTPException(422, "Nivel de alerta inválido.")
    if "status" in fields and fields["status"] not in STATUSES:
        raise HTTPException(422, "Estado inválido.")
    if "expires_at" in fields:
        fields["expires_at"] = norm_dt(fields["expires_at"])
    for k in ("full_name", "reason", "legal_basis"):
        if k in fields:
            fields[k] = str(fields[k]).strip()[:300]
    for k in ("info", "notes"):
        if k in fields:
            fields[k] = str(fields[k]).strip()[:2000]
    return fields


def _classification_fields(classification: str, consent: bool, user: dict, fields: dict) -> dict:
    """Campos que exige cada clasificación.

    Una persona autorizada necesita consentimiento confirmado. Una no autorizada
    necesita motivo, base legal y nivel propios: nunca se heredan valores.
    """
    if classification not in CLASSIFICATIONS:
        raise HTTPException(422, "Clasificación inválida.")
    if classification == "autorizada":
        if not consent:
            raise HTTPException(422, "Confirme el consentimiento de la persona para registrarla como autorizada.")
        return {"reason": AUTHORIZED_REASON, "legal_basis": f"Consentimiento confirmado por {user['username']}",
                "alert_level": "bajo"}
    missing = [k for k in ("reason", "legal_basis", "alert_level") if not str(fields.get(k) or "").strip()]
    if missing:
        raise HTTPException(422, "Una persona no autorizada requiere motivo, base legal y nivel de alerta.")
    return {}


def _history(db: Any, person_id: int, user: dict, action: str, changes: dict, now: str) -> None:
    db.execute("INSERT INTO person_history (entry_id, user_id, username, action, changes, at) VALUES (?,?,?,?,?,?)",
               (person_id, user["id"], user["username"], action, json.dumps(changes, ensure_ascii=False), now))


def _image_response(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg" if data[:2] == b"\xff\xd8" else "image/png",
                    headers={"Cache-Control": "no-store, private"})


@router.get("")
def list_entries(
    q: str = "", level: str = "", status: str = "", simulated: str = "", classification: str = "",
    page: int = 1, page_size: int = 25, user: dict = Depends(require("blacklist.view")),
):
    where, params = ["1=1"], []
    if q:
        where.append("(p.full_name LIKE ? OR p.uid LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if level in LEVELS:
        where.append("p.alert_level = ?"); params.append(level)
    if status in STATUSES:
        where.append("p.status = ?"); params.append(status)
    if simulated in ("0", "1"):
        where.append("p.is_simulated = ?"); params.append(int(simulated))
    scope, scope_params = "1=1", []
    if classification in CLASSIFICATIONS:
        where.append("p.classification = ?"); params.append(classification)
        scope, scope_params = "classification = ?", [classification]
    limit, offset = paginate(page, page_size)
    w = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) AS n FROM persons p WHERE {w}", tuple(params))["n"]
    rows = query(f"{PERSON_SELECT} WHERE {w} ORDER BY p.updated_at DESC, p.id DESC LIMIT ? OFFSET ?", (*params, limit, offset))
    stats = query(f"SELECT alert_level, status, classification, COUNT(*) AS n FROM persons WHERE {scope} "
                  "GROUP BY alert_level, status, classification", tuple(scope_params))
    return {"items": [_serialize(r, user) for r in rows], "total": total, "page": page, "page_size": limit, "stats": stats}


@router.post("/validate-photo")
async def validate_photo(photo: UploadFile = File(...), user: dict = Depends(require("blacklist.edit"))):
    data = await read_photo(photo)
    report = await run_in_threadpool(engine.analyze_photo, data)
    out = _public_report(report)
    out["duplicates"] = find_similar(report["embedding"], settings.get("match_threshold")) if report["ok"] else []
    return out


@router.post("")
async def create_entry(
    request: Request,
    full_name: str = Form(...), expires_at: str = Form(...), classification: str = Form("no_autorizada"),
    reason: str = Form(""), legal_basis: str = Form(""), alert_level: str = Form(""), info: str = Form(""),
    notes: str = Form(""), consent: bool = Form(False), confirm_duplicate: bool = Form(False),
    photo: UploadFile = File(...), user: dict = Depends(require("blacklist.edit")),
):
    fields = {"full_name": full_name, "reason": reason, "legal_basis": legal_basis, "alert_level": alert_level,
              "expires_at": expires_at, "info": info, "notes": notes}
    fields.update(_classification_fields(classification, consent, user, fields))
    fields = _validate_fields(fields)
    if fields["expires_at"] <= utcnow():
        raise HTTPException(422, "La fecha de vencimiento debe ser futura.")
    data = await read_photo(photo)
    report = await run_in_threadpool(_validated_report, data)
    _check_duplicates(report, confirm_duplicate)
    now = utcnow()
    uid = f"FG-{secrets.token_hex(3).upper()}"
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO persons (uid, full_name, info, reason, legal_basis, alert_level, registered_at, expires_at,
                 status, notes, classification, created_by, updated_at)
               VALUES (?,?,?,?,?,?,?,?, 'activo', ?,?,?,?)""",
            (uid, fields["full_name"], fields["info"], fields["reason"], fields["legal_basis"], fields["alert_level"],
             now, fields["expires_at"], fields["notes"], classification, user["id"], now))
        entry_id = cur.lastrowid
        insert_sample(db, entry_id, data, report, user["id"], primary=True)
        _history(db, entry_id, user, "creado", {**fields, "classification": classification}, now)
    gallery.load()
    audit(user, "registro de persona", target=uid,
          details={"clasificación": classification, "nivel": fields["alert_level"]}, ip=client_ip(request))
    return _serialize(_person(entry_id), user)


@router.post("/deactivate-expired")
def deactivate_expired(request: Request, user: dict = Depends(require("blacklist.edit"))):
    from app.services.retention import run_retention
    result = run_retention()
    audit(user, "desactivar registros vencidos", details=result, ip=client_ip(request))
    return result


@router.get("/{entry_id}")
def get_entry(entry_id: int, user: dict = Depends(require("blacklist.view"))):
    out = _serialize(_person(entry_id), user)
    out["samples"] = [
        {**s, "is_primary": bool(s["is_primary"]), "quality": json.loads(s["quality"]) if s["quality"] else None}
        for s in query("SELECT id, is_primary, model_version, quality, created_at FROM face_samples "
                       "WHERE person_id = ? ORDER BY is_primary DESC, id", (entry_id,))
    ]
    out["history"] = query("SELECT username, action, changes, at FROM person_history WHERE entry_id = ? ORDER BY at DESC, id DESC",
                           (entry_id,))
    out["alerts"] = query("SELECT uid, occurred_at, score, review_status FROM events WHERE entry_id = ? AND type='coincidencia' "
                          "ORDER BY occurred_at DESC LIMIT 20", (entry_id,))
    return out


@router.put("/{entry_id}")
async def update_entry(
    entry_id: int, request: Request,
    full_name: str | None = Form(None), reason: str | None = Form(None), legal_basis: str | None = Form(None),
    alert_level: str | None = Form(None), expires_at: str | None = Form(None), info: str | None = Form(None),
    notes: str | None = Form(None), status: str | None = Form(None), classification: str | None = Form(None),
    consent: bool = Form(False), photo: UploadFile | None = File(None), user: dict = Depends(require("blacklist.edit")),
):
    row = _person(entry_id)
    incoming = {"full_name": full_name, "reason": reason, "legal_basis": legal_basis, "alert_level": alert_level,
                "expires_at": expires_at, "info": info, "notes": notes, "status": status}
    fields = {k: v for k, v in incoming.items() if v is not None}
    if classification is not None and classification != row["classification"]:
        fields.update(_classification_fields(classification, consent, user, fields))
        fields["classification"] = classification
    fields = _validate_fields(fields)
    if fields.get("status") == "activo" and (fields.get("expires_at") or row["expires_at"]) <= utcnow():
        raise HTTPException(422, "No se puede activar un registro vencido: actualice la fecha de revisión.")
    changes = {k: [row[k], v] for k, v in fields.items() if row[k] != v}
    data = report = None
    if photo is not None and photo.filename:
        data = await read_photo(photo)
        report = await run_in_threadpool(_validated_report, data)
        if query_one("SELECT id FROM face_samples WHERE person_id = ? AND content_hash = ?", (entry_id, content_hash(data))):
            raise HTTPException(409, "Esta fotografía ya está registrada para esta persona.")
        changes["fotografía"] = ["anterior", "reemplazada"]
    if not changes:
        return _serialize(row, user)
    now = utcnow()
    old_file = None
    with get_db() as db:
        sets = [f"{k} = ?" for k in fields if k in changes]
        params = [changes[k][1] for k in fields if k in changes]
        db.execute(f"UPDATE persons SET {', '.join([*sets, 'updated_at = ?'])} WHERE id = ?", (*params, now, entry_id))
        if report is not None:
            old = db.execute("SELECT id, photo_file FROM face_samples WHERE person_id = ? AND is_primary = 1", (entry_id,)).fetchone()
            if old:
                db.execute("DELETE FROM face_samples WHERE id = ?", (old["id"],))
                old_file = old["photo_file"]
            insert_sample(db, entry_id, data, report, user["id"], primary=True)
        _history(db, entry_id, user, "modificado", changes, now)
    secure_delete(old_file)
    gallery.load()
    audit(user, "modificación de registro", target=row["uid"], details=list(changes), ip=client_ip(request))
    return _serialize(_person(entry_id), user)


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, request: Request, user: dict = Depends(require("blacklist.edit"))):
    """Eliminación definitiva: borra de forma segura las fotos y las plantillas."""
    row = _person(entry_id)
    files = [r["photo_file"] for r in query("SELECT photo_file FROM face_samples WHERE person_id = ?", (entry_id,))]
    with get_db() as db:
        db.execute("DELETE FROM persons WHERE id = ?", (entry_id,))
    for name in files:
        secure_delete(name)
    gallery.load()
    audit(user, "eliminación de registro", target=row["uid"], details={"nombre": row["full_name"]}, ip=client_ip(request))
    return {"ok": True}


@router.get("/{entry_id}/photo")
def get_photo(entry_id: int, request: Request, user: dict = Depends(require("blacklist.view"))):
    _check_photo_access(user)
    name = primary_photo_file(entry_id)
    data = read_encrypted_file(name) if name else None
    if data is None:
        raise HTTPException(404, "Sin fotografía.")
    return _image_response(data)


# ------------------------------------------------------------ muestras faciales
def _sample(entry_id: int, sample_id: int) -> dict:
    row = query_one("SELECT * FROM face_samples WHERE id = ? AND person_id = ?", (sample_id, entry_id))
    if not row:
        raise HTTPException(404, "Fotografía no encontrada.")
    return row


@router.post("/{entry_id}/samples")
async def add_sample(
    entry_id: int, request: Request, photo: UploadFile = File(...), confirm_duplicate: bool = Form(False),
    user: dict = Depends(require("blacklist.edit")),
):
    row = _person(entry_id)
    data = await read_photo(photo)
    if query_one("SELECT id FROM face_samples WHERE person_id = ? AND content_hash = ?", (entry_id, content_hash(data))):
        raise HTTPException(409, "Esta fotografía ya está registrada para esta persona.")
    report = await run_in_threadpool(_validated_report, data)
    _check_duplicates(report, confirm_duplicate, exclude=entry_id)
    now = utcnow()
    with get_db() as db:
        sample_id, _ = insert_sample(db, entry_id, data, report, user["id"], primary=row["sample_count"] == 0)
        db.execute("UPDATE persons SET updated_at = ? WHERE id = ?", (now, entry_id))
        _history(db, entry_id, user, "fotografía añadida", {"muestra": sample_id}, now)
    gallery.load()
    audit(user, "añadir fotografía", target=row["uid"], ip=client_ip(request))
    return {"id": sample_id}


@router.post("/{entry_id}/samples/{sample_id}/primary")
def set_primary(entry_id: int, sample_id: int, request: Request, user: dict = Depends(require("blacklist.edit"))):
    row = _person(entry_id)
    _sample(entry_id, sample_id)
    now = utcnow()
    with get_db() as db:
        db.execute("UPDATE face_samples SET is_primary = 0 WHERE person_id = ?", (entry_id,))
        db.execute("UPDATE face_samples SET is_primary = 1 WHERE id = ?", (sample_id,))
        _history(db, entry_id, user, "fotografía principal cambiada", {"muestra": sample_id}, now)
    audit(user, "cambiar fotografía principal", target=row["uid"], ip=client_ip(request))
    return {"ok": True}


@router.delete("/{entry_id}/samples/{sample_id}")
def delete_sample(entry_id: int, sample_id: int, request: Request, user: dict = Depends(require("blacklist.edit"))):
    row = _person(entry_id)
    sample = _sample(entry_id, sample_id)
    if row["sample_count"] <= 1:
        raise HTTPException(409, "Es la única fotografía. Reemplácela o elimine el registro.")
    now = utcnow()
    with get_db() as db:
        db.execute("DELETE FROM face_samples WHERE id = ?", (sample_id,))
        if sample["is_primary"]:
            db.execute("""UPDATE face_samples SET is_primary = 1 WHERE id =
                          (SELECT MIN(id) FROM face_samples WHERE person_id = ?)""", (entry_id,))
        _history(db, entry_id, user, "fotografía eliminada", {"muestra": sample_id}, now)
    secure_delete(sample["photo_file"])
    gallery.load()
    audit(user, "eliminar fotografía", target=row["uid"], ip=client_ip(request))
    return {"ok": True}


@router.get("/{entry_id}/samples/{sample_id}/photo")
def get_sample_photo(entry_id: int, sample_id: int, user: dict = Depends(require("blacklist.view"))):
    _check_photo_access(user)
    data = read_encrypted_file(_sample(entry_id, sample_id)["photo_file"])
    if data is None:
        raise HTTPException(404, "Archivo no disponible.")
    return _image_response(data)


def _check_photo_access(user: dict) -> None:
    if has_perm(user, "blacklist.photos"):
        return
    raise HTTPException(403, "No tiene permisos para ver fotografías.")


# Operadores: ven la foto registrada solo en el contexto de una alerta.
photo_for_alert_router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@photo_for_alert_router.get("/{event_id}/registered-photo")
def registered_photo(event_id: int, request: Request, user: dict = Depends(require("alerts.images"))):
    ev = query_one("SELECT uid, entry_id FROM events WHERE id = ? AND type='coincidencia'", (event_id,))
    if not ev or not ev["entry_id"]:
        raise HTTPException(404, "Sin fotografía registrada.")
    name = primary_photo_file(ev["entry_id"])
    data = read_encrypted_file(name) if name else None
    if data is None:
        raise HTTPException(404, "Archivo no disponible.")
    audit(user, "ver fotografía registrada", target=ev["uid"], ip=client_ip(request))
    return _image_response(data)
