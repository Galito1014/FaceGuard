"""Asistente de primer uso y comprobación de actualizaciones."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import config
from app.core.audit import audit
from app.core.database import execute, query_one, utcnow
from app.core.network import is_loopback
from app.core.security import COOKIE_NAME, client_ip, create_session, hash_password, require, validate_password_strength
from app.services import setup as setup_service
from app.services import updates
from app.services.settings_store import settings

router = APIRouter(tags=["setup"])

# Parámetros que el asistente puede fijar. El resto se cambia luego en Configuración.
SETUP_SETTINGS = {"camera_index", "camera_width", "camera_height", "match_threshold", "confirm_frames",
                  "monitoring_enabled", "alerts_enabled", "alert_sound", "gpio_enabled",
                  "retention_days_events", "retention_days_snapshots", "update_check"}


class SetupIn(BaseModel):
    setup_code: str | None = Field(default=None, max_length=32)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)
    privacy_ack: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


def _code_required(request: Request) -> bool:
    return not is_loopback(client_ip(request))


@router.get("/api/setup/status")
def setup_status(request: Request):
    pending = setup_service.needs_setup()
    data: dict[str, Any] = {"needs_setup": pending, "edition": config.edition, "version": config.version}
    if pending:
        setup_service.ensure_setup_code()
        data["code_required"] = _code_required(request)
        data["defaults"] = {k: settings.get(k) for k in sorted(SETUP_SETTINGS)}
        # Las cámaras solo se listan desde el propio equipo o con el código correcto
        # (ver /api/setup/cameras), para no revelar hardware a la red.
    return data


class CamerasIn(BaseModel):
    setup_code: str | None = Field(default=None, max_length=32)


@router.post("/api/setup/cameras")
def setup_cameras(body: CamerasIn, request: Request):
    if not setup_service.needs_setup():
        raise HTTPException(409, "FaceGuard AI ya está configurado.")
    _check_code(request, body.setup_code)
    from app.services.camera import list_cameras
    try:
        return {"cameras": list_cameras()}
    except Exception:
        return {"cameras": []}


def _check_code(request: Request, code: str | None) -> None:
    if not _code_required(request):
        return
    if setup_service.blocked():
        raise HTTPException(429, "Demasiados intentos con un código incorrecto. Espere 5 minutos.")
    if not setup_service.check_code(code):
        raise HTTPException(403, "El código de configuración no es correcto.")


@router.post("/api/setup")
def run_setup(body: SetupIn, request: Request, response: Response):
    ip = client_ip(request)
    with setup_service.creation_lock:
        if not setup_service.needs_setup():
            raise HTTPException(409, "FaceGuard AI ya está configurado. Inicie sesión.")
        _check_code(request, body.setup_code)
        if not body.privacy_ack:
            raise HTTPException(400, "Debe aceptar el aviso de privacidad y uso responsable para continuar.")
        problem = validate_password_strength(body.password)
        if problem:
            raise HTTPException(400, problem)
        unknown = set(body.settings) - SETUP_SETTINGS
        if unknown:
            raise HTTPException(400, f"Parámetros no permitidos en el asistente: {', '.join(sorted(unknown))}")
        try:
            clean = {k: settings.validate(k, v) for k, v in body.settings.items()}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        execute("INSERT INTO users (username, full_name, password_hash, role, active, must_change_password, created_at) "
                "VALUES (?,?,?,?,1,0,?)",
                (body.username, body.full_name.strip(), hash_password(body.password), "superadmin", utcnow()))
        user = query_one("SELECT * FROM users WHERE username = ?", (body.username,))
        setup_service.finish()
    if clean:
        settings.update(clean)
    audit(user, "configuración inicial completada", details={"edicion": config.edition, "parametros": clean}, ip=ip)
    audit(user, "aviso de privacidad aceptado", details={"version": config.version}, ip=ip)
    token = create_session(user["id"], ip, request.headers.get("user-agent"))
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", secure=config.secure_cookies,
                        max_age=config.session_hours * 3600, path="/")
    return {"ok": True}


@router.get("/api/system/update")
def check_update(force: bool = False, user: dict = Depends(require("settings.view"))):
    if not settings.get("update_check"):
        return {"current": config.version, "edition": config.edition, "enabled": False, "update_available": False,
                "url": f"https://github.com/{config.update_repo}/releases"}
    return {**updates.check(force=force), "enabled": True}
