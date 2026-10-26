"""Usuarios, auditoría, configuración, sistema y modo demostración."""
from __future__ import annotations

from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.common import norm_dt, paginate
from app.config import config
from app.core.audit import audit
from app.core.database import execute, query, query_one, utcnow
from app.core.security import ROLE_LABELS, ROLES, client_ip, hash_password, require, validate_password_strength
from app.services import demo, runtime, system_monitor
from app.services.camera import list_cameras
from app.services.gpio import gpio
from app.services.pipeline import pipeline
from app.services.retention import run_retention
from app.services.settings_store import settings

router = APIRouter(tags=["admin"])


# ------------------------------------------------------------------ usuarios
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=3, max_length=100)
    role: str
    password: str = Field(max_length=256)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=100)
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


def _public_user(r: dict) -> dict:
    return {k: r[k] for k in ("id", "username", "full_name", "role", "active", "must_change_password", "created_at",
                              "last_login")} | {"role_label": ROLE_LABELS[r["role"]]}


@router.get("/api/users")
def list_users(user: dict = Depends(require("users.manage"))):
    return [_public_user(r) for r in query("SELECT * FROM users ORDER BY role, username")]


@router.post("/api/users")
def create_user(body: UserIn, request: Request, user: dict = Depends(require("users.manage"))):
    if body.role not in ROLES:
        raise HTTPException(422, "Rol inválido.")
    if query_one("SELECT id FROM users WHERE username = ?", (body.username,)):
        raise HTTPException(409, "Ese nombre de usuario ya existe.")
    problem = validate_password_strength(body.password)
    if problem:
        raise HTTPException(422, problem)
    uid = execute("INSERT INTO users (username, full_name, password_hash, role, active, must_change_password, created_at) "
                  "VALUES (?,?,?,?,1,1,?)", (body.username, body.full_name, hash_password(body.password), body.role, utcnow()))
    audit(user, "crear usuario", target=body.username, details={"rol": body.role}, ip=client_ip(request))
    return _public_user(query_one("SELECT * FROM users WHERE id = ?", (uid,)))


def _superadmins_left(excluding: int) -> int:
    return query_one("SELECT COUNT(*) AS n FROM users WHERE role='superadmin' AND active=1 AND id != ?", (excluding,))["n"]


@router.put("/api/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, user: dict = Depends(require("users.manage"))):
    target = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not target:
        raise HTTPException(404, "Usuario no encontrado.")
    sets, params, changes = [], [], {}
    if body.full_name is not None:
        sets.append("full_name = ?"); params.append(body.full_name); changes["nombre"] = body.full_name
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, "Rol inválido.")
        if target["role"] == "superadmin" and body.role != "superadmin" and _superadmins_left(user_id) == 0:
            raise HTTPException(409, "Debe existir al menos un superadministrador activo.")
        sets.append("role = ?"); params.append(body.role); changes["rol"] = body.role
    if body.active is not None:
        if not body.active and user_id == user["id"]:
            raise HTTPException(409, "No puede desactivar su propia cuenta.")
        if not body.active and target["role"] == "superadmin" and _superadmins_left(user_id) == 0:
            raise HTTPException(409, "Debe existir al menos un superadministrador activo.")
        sets.append("active = ?"); params.append(int(body.active)); changes["activo"] = body.active
    if body.password:
        problem = validate_password_strength(body.password)
        if problem:
            raise HTTPException(422, problem)
        sets += ["password_hash = ?", "must_change_password = 1"]; params.append(hash_password(body.password))
        changes["contraseña"] = "restablecida"
    if not sets:
        return _public_user(target)
    execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*params, user_id))
    if body.active is False or body.password or body.role:
        execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))  # fuerza nuevo inicio de sesión
    audit(user, "modificar usuario", target=target["username"], details=changes, ip=client_ip(request))
    return _public_user(query_one("SELECT * FROM users WHERE id = ?", (user_id,)))


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, user: dict = Depends(require("users.manage"))):
    target = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not target:
        raise HTTPException(404, "Usuario no encontrado.")
    if user_id == user["id"]:
        raise HTTPException(409, "No puede eliminar su propia cuenta.")
    if target["role"] == "superadmin" and _superadmins_left(user_id) == 0:
        raise HTTPException(409, "Debe existir al menos un superadministrador activo.")
    # Se conserva la trazabilidad: los registros guardan el nombre del revisor.
    execute("UPDATE events SET reviewed_by = NULL WHERE reviewed_by = ?", (user_id,))
    execute("UPDATE blacklist SET created_by = NULL WHERE created_by = ?", (user_id,))
    execute("UPDATE blacklist_history SET user_id = NULL WHERE user_id = ?", (user_id,))
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    audit(user, "eliminar usuario", target=target["username"], ip=client_ip(request))
    return {"ok": True}


# ---------------------------------------------------------------- auditoría
@router.get("/api/audit")
def list_audit(q: str = "", date_from: str | None = None, date_to: str | None = None, page: int = 1,
               page_size: int = 50, user: dict = Depends(require("audit.view"))):
    where, params = ["1=1"], []
    if q:
        where.append("(username LIKE ? OR action LIKE ? OR target LIKE ?)"); params += [f"%{q}%"] * 3
    if date_from:
        where.append("at >= ?"); params.append(norm_dt(date_from))
    if date_to:
        where.append("at <= ?"); params.append(norm_dt(date_to))
    limit, offset = paginate(page, page_size)
    w = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) AS n FROM audit_log WHERE {w}", tuple(params))["n"]
    rows = query(f"SELECT * FROM audit_log WHERE {w} ORDER BY at DESC, id DESC LIMIT ? OFFSET ?", (*params, limit, offset))
    return {"items": rows, "total": total, "page": page, "page_size": limit}


# ------------------------------------------------------------- configuración
@router.get("/api/settings")
def get_settings(user: dict = Depends(require("settings.view"))):
    return {"values": settings.all(), "cameras": list_cameras(), "gpio": gpio.status(),
            "can_edit": user["role"] == "superadmin"}


@router.put("/api/settings")
def put_settings(changes: dict, request: Request, user: dict = Depends(require("settings.edit"))):
    try:
        changed = settings.update(changes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if changed:
        audit(user, "modificar configuración", details=changed, ip=client_ip(request))
    return {"values": settings.all(), "changed": changed}


@router.post("/api/settings/gpio-test")
def gpio_test(request: Request, user: dict = Depends(require("settings.edit"))):
    audit(user, "prueba de LED y buzzer", ip=client_ip(request))
    return gpio.test(settings.all())


# ---------------------------------------------------------------- sistema
@router.get("/api/system/info")
def system_info(user: dict = Depends(require("settings.view"))):
    from app.core.database import query as q
    db_size = config.db_path.stat().st_size if config.db_path.exists() else 0
    migrations = q("SELECT version, applied_at FROM schema_migrations ORDER BY version")
    return {"device": system_monitor.info(), "status": system_monitor.snapshot(), "engine": pipeline.status(),
            "app_version": config.version, "db_size_kb": round(db_size / 1024), "migrations": migrations,
            "data_dir": str(config.data_dir)}


@router.get("/api/system/logs")
def system_logs(lines: int = 200, user: dict = Depends(require("system.control"))):
    path = config.log_dir / "faceguard.log"
    if not path.exists():
        return {"lines": []}
    with open(path, encoding="utf-8", errors="replace") as fh:
        return {"lines": list(deque(fh, maxlen=min(max(lines, 10), 1000)))}


@router.post("/api/system/engine/restart")
def engine_restart(request: Request, user: dict = Depends(require("system.control"))):
    result = runtime.restart_engine()
    audit(user, "reiniciar motor de reconocimiento", details=result, ip=client_ip(request))
    return result


@router.post("/api/system/retention/run")
def retention_now(request: Request, user: dict = Depends(require("system.control"))):
    result = run_retention()
    audit(user, "ejecutar retención manual", details=result, ip=client_ip(request))
    return result


# ------------------------------------------------------------ demostración
@router.post("/api/demo/seed")
def demo_seed(request: Request, user: dict = Depends(require("demo.control"))):
    result = demo.seed(user)
    audit(user, "cargar datos de demostración", details=result, ip=client_ip(request))
    return result


@router.post("/api/demo/clear")
def demo_clear(request: Request, user: dict = Depends(require("demo.control"))):
    result = demo.clear()
    audit(user, "eliminar datos de demostración", details=result, ip=client_ip(request))
    return result


@router.post("/api/demo/alert")
def demo_alert(request: Request, user: dict = Depends(require("demo.control"))):
    row = pipeline.simulate_alert()
    audit(user, "generar alerta de prueba", target=row["uid"] if row else "", ip=client_ip(request))
    from app.services.events import serialize_event
    return serialize_event(row) if row else {}
