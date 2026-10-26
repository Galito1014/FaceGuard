from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from app.api.common import norm_dt, paginate
from app.core.audit import audit
from app.core.crypto import encrypt_embedding, read_encrypted_file, save_encrypted_file, secure_delete
from app.core.database import get_db, query, query_one, utcnow
from app.core.security import client_ip, has_perm, require
from app.services.face_engine import engine, gallery

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])

MAX_PHOTO_BYTES = 6 * 1024 * 1024
LEVELS = {"bajo", "medio", "alto"}
STATUSES = {"activo", "inactivo", "vencido"}
EDITABLE = ("full_name", "info", "reason", "legal_basis", "alert_level", "expires_at", "status", "notes")


def _serialize(row: dict, user: dict) -> dict:
    out = {k: v for k, v in row.items() if k not in ("embedding_enc", "photo_file")}
    out["has_photo"] = bool(row.get("photo_file"))
    out["has_template"] = row.get("embedding_enc") is not None
    out["is_simulated"] = bool(row["is_simulated"])
    out["photo_quality"] = json.loads(row["photo_quality"]) if row.get("photo_quality") else None
    out["can_view_photo"] = has_perm(user, "blacklist.photos")
    return out


async def _read_photo(photo: UploadFile) -> bytes:
    data = await photo.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "La fotografía supera 6 MB.")
    if not data[:3] == b"\xff\xd8\xff" and not data[:8] == b"\x89PNG\r\n\x1a\n":
        raise HTTPException(415, "Formato no admitido. Use JPG o PNG.")
    return data


def _public_report(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "embedding"}


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


@router.get("")
def list_entries(
    q: str = "", level: str = "", status: str = "", simulated: str = "",
    page: int = 1, page_size: int = 25, user: dict = Depends(require("blacklist.view")),
):
    where, params = ["1=1"], []
    if q:
        where.append("(full_name LIKE ? OR uid LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if level in LEVELS:
        where.append("alert_level = ?"); params.append(level)
    if status in STATUSES:
        where.append("status = ?"); params.append(status)
    if simulated in ("0", "1"):
        where.append("is_simulated = ?"); params.append(int(simulated))
    limit, offset = paginate(page, page_size)
    w = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) AS n FROM blacklist WHERE {w}", tuple(params))["n"]
    rows = query(f"SELECT * FROM blacklist WHERE {w} ORDER BY updated_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))
    stats = query("SELECT alert_level, status, COUNT(*) AS n FROM blacklist GROUP BY alert_level, status")
    return {"items": [_serialize(r, user) for r in rows], "total": total, "page": page, "page_size": limit, "stats": stats}


@router.post("/validate-photo")
async def validate_photo(photo: UploadFile = File(...), user: dict = Depends(require("blacklist.edit"))):
    data = await _read_photo(photo)
    return _public_report(engine.analyze_photo(data))


@router.post("")
async def create_entry(
    request: Request,
    full_name: str = Form(...), reason: str = Form(...), legal_basis: str = Form(...),
    alert_level: str = Form(...), expires_at: str = Form(...), info: str = Form(""), notes: str = Form(""),
    photo: UploadFile = File(...), user: dict = Depends(require("blacklist.edit")),
):
    fields = _validate_fields({"full_name": full_name, "reason": reason, "legal_basis": legal_basis,
                               "alert_level": alert_level, "expires_at": expires_at, "info": info, "notes": notes})
    if fields["expires_at"] <= utcnow():
        raise HTTPException(422, "La fecha de vencimiento debe ser futura.")
    data = await _read_photo(photo)
    report = engine.analyze_photo(data)
    if not report["ok"]:
        raise HTTPException(422, {"message": "La fotografía no cumple los requisitos de calidad.", "report": _public_report(report)})
    photo_file = save_encrypted_file("photos", data)
    now = utcnow()
    uid = f"FG-{secrets.token_hex(3).upper()}"
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO blacklist (uid, full_name, info, reason, legal_basis, alert_level, registered_at, expires_at,
                 status, notes, photo_file, embedding_enc, photo_quality, created_by, updated_at)
               VALUES (?,?,?,?,?,?,?,?, 'activo', ?,?,?,?,?,?)""",
            (uid, fields["full_name"], fields["info"], fields["reason"], fields["legal_basis"], fields["alert_level"],
             now, fields["expires_at"], fields["notes"], photo_file, encrypt_embedding(report["embedding"]),
             json.dumps(report.get("metrics", {})), user["id"], now))
        entry_id = cur.lastrowid
        safe = {k: v for k, v in fields.items()}
        db.execute("INSERT INTO blacklist_history (entry_id, user_id, username, action, changes, at) VALUES (?,?,?,?,?,?)",
                   (entry_id, user["id"], user["username"], "creado", json.dumps(safe, ensure_ascii=False), now))
    gallery.load()
    audit(user, "registro en lista de alerta", target=uid, details={"nivel": fields["alert_level"]}, ip=client_ip(request))
    return _serialize(query_one("SELECT * FROM blacklist WHERE id = ?", (entry_id,)), user)


@router.get("/{entry_id}")
def get_entry(entry_id: int, user: dict = Depends(require("blacklist.view"))):
    row = query_one("SELECT * FROM blacklist WHERE id = ?", (entry_id,))
    if not row:
        raise HTTPException(404, "Registro no encontrado.")
    out = _serialize(row, user)
    out["history"] = query("SELECT username, action, changes, at FROM blacklist_history WHERE entry_id = ? ORDER BY at DESC, id DESC",
                           (entry_id,))
    out["alerts"] = query("SELECT uid, occurred_at, score, review_status FROM events WHERE entry_id = ? AND type='coincidencia' "
                          "ORDER BY occurred_at DESC LIMIT 20", (entry_id,))
    return out


@router.put("/{entry_id}")
async def update_entry(
    entry_id: int, request: Request,
    full_name: str | None = Form(None), reason: str | None = Form(None), legal_basis: str | None = Form(None),
    alert_level: str | None = Form(None), expires_at: str | None = Form(None), info: str | None = Form(None),
    notes: str | None = Form(None), status: str | None = Form(None),
    photo: UploadFile | None = File(None), user: dict = Depends(require("blacklist.edit")),
):
    row = query_one("SELECT * FROM blacklist WHERE id = ?", (entry_id,))
    if not row:
        raise HTTPException(404, "Registro no encontrado.")
    incoming = {"full_name": full_name, "reason": reason, "legal_basis": legal_basis, "alert_level": alert_level,
                "expires_at": expires_at, "info": info, "notes": notes, "status": status}
    fields = _validate_fields({k: v for k, v in incoming.items() if v is not None})
    if fields.get("status") == "activo" and (fields.get("expires_at") or row["expires_at"]) <= utcnow():
        raise HTTPException(422, "No se puede activar un registro vencido: actualice la fecha de revisión.")
    changes = {k: [row[k], v] for k, v in fields.items() if row[k] != v}
    sets, params = [f"{k} = ?" for k in changes], [v[1] for v in changes.values()]
    old_photo = None
    if photo is not None and photo.filename:
        data = await _read_photo(photo)
        report = engine.analyze_photo(data)
        if not report["ok"]:
            raise HTTPException(422, {"message": "La fotografía no cumple los requisitos de calidad.", "report": _public_report(report)})
        new_file = save_encrypted_file("photos", data)
        sets += ["photo_file = ?", "embedding_enc = ?", "photo_quality = ?"]
        params += [new_file, encrypt_embedding(report["embedding"]), json.dumps(report.get("metrics", {}))]
        changes["fotografía"] = ["anterior", "reemplazada"]
        old_photo = row["photo_file"]
    if not changes:
        return _serialize(row, user)
    now = utcnow()
    with get_db() as db:
        db.execute(f"UPDATE blacklist SET {', '.join(sets)}, updated_at = ? WHERE id = ?", (*params, now, entry_id))
        db.execute("INSERT INTO blacklist_history (entry_id, user_id, username, action, changes, at) VALUES (?,?,?,?,?,?)",
                   (entry_id, user["id"], user["username"], "modificado", json.dumps(changes, ensure_ascii=False), now))
    secure_delete(old_photo)
    gallery.load()
    audit(user, "modificación de registro", target=row["uid"], details=list(changes), ip=client_ip(request))
    return _serialize(query_one("SELECT * FROM blacklist WHERE id = ?", (entry_id,)), user)


@router.delete("/{entry_id}")
def delete_entry(entry_id: int, request: Request, user: dict = Depends(require("blacklist.edit"))):
    """Eliminación definitiva: borra de forma segura la foto y la plantilla."""
    row = query_one("SELECT * FROM blacklist WHERE id = ?", (entry_id,))
    if not row:
        raise HTTPException(404, "Registro no encontrado.")
    with get_db() as db:
        db.execute("DELETE FROM blacklist WHERE id = ?", (entry_id,))
    secure_delete(row["photo_file"])
    gallery.load()
    audit(user, "eliminación de registro", target=row["uid"], details={"nombre": row["full_name"]}, ip=client_ip(request))
    return {"ok": True}


@router.post("/deactivate-expired")
def deactivate_expired(request: Request, user: dict = Depends(require("blacklist.edit"))):
    from app.services.retention import run_retention
    result = run_retention()
    audit(user, "desactivar registros vencidos", details=result, ip=client_ip(request))
    return result


@router.get("/{entry_id}/photo")
def get_photo(entry_id: int, request: Request, user: dict = Depends(require("blacklist.view"))):
    _check_photo_access(entry_id, user)
    row = query_one("SELECT uid, photo_file FROM blacklist WHERE id = ?", (entry_id,))
    if not row or not row["photo_file"]:
        raise HTTPException(404, "Sin fotografía.")
    data = read_encrypted_file(row["photo_file"])
    if data is None:
        raise HTTPException(404, "Archivo no disponible.")
    return Response(data, media_type="image/jpeg" if data[:2] == b"\xff\xd8" else "image/png",
                    headers={"Cache-Control": "no-store, private"})


def _check_photo_access(entry_id: int, user: dict) -> None:
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
    row = query_one("SELECT photo_file FROM blacklist WHERE id = ?", (ev["entry_id"],))
    data = read_encrypted_file(row["photo_file"]) if row and row["photo_file"] else None
    if data is None:
        raise HTTPException(404, "Archivo no disponible.")
    audit(user, "ver fotografía registrada", target=ev["uid"], ip=client_ip(request))
    return Response(data, media_type="image/jpeg" if data[:2] == b"\xff\xd8" else "image/png",
                    headers={"Cache-Control": "no-store, private"})
