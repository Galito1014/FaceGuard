from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import config
from app.core.audit import audit
from app.core.database import execute, query_one, utcnow
from app.core.security import (COOKIE_NAME, ROLE_LABELS, client_ip, create_session, current_user, destroy_session,
                               hash_password, permissions_for, throttle, validate_password_strength, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(max_length=256)


def _me(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "role_label": ROLE_LABELS[user["role"]],
        "must_change_password": bool(user["must_change_password"]),
        "permissions": permissions_for(user["role"]),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = client_ip(request)
    if throttle.is_blocked(body.username, ip):
        raise HTTPException(429, f"Demasiados intentos fallidos. Espere {max(1, throttle.WINDOW // 60)} minuto(s).")
    user = query_one("SELECT * FROM users WHERE username = ?", (body.username,))
    if not user or not user["active"] or not verify_password(body.password, user["password_hash"]):
        throttle.fail(body.username, ip)
        audit({"id": user["id"] if user else None, "username": body.username}, "inicio de sesión fallido", ip=ip)
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    throttle.reset(body.username, ip)
    token = create_session(user["id"], ip, request.headers.get("user-agent"))
    execute("UPDATE users SET last_login = ? WHERE id = ?", (utcnow(), user["id"]))
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict", secure=config.secure_cookies,
                        max_age=config.session_hours * 3600, path="/")
    audit(user, "inicio de sesión", ip=ip)
    return _me(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    from app.core.security import user_from_token
    user = user_from_token(token)
    destroy_session(token)
    response.delete_cookie(COOKIE_NAME, path="/")
    if user:
        audit(user, "cierre de sesión", ip=client_ip(request))
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return _me(user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, user: dict = Depends(current_user)):
    row = query_one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(400, "La contraseña actual no es correcta.")
    if body.new_password == body.current_password:
        raise HTTPException(400, "La nueva contraseña debe ser distinta de la actual.")
    problem = validate_password_strength(body.new_password)
    if problem:
        raise HTTPException(400, problem)
    execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (hash_password(body.new_password), user["id"]))
    # Cierra las demás sesiones del usuario.
    token = request.cookies.get(COOKIE_NAME)
    from app.core.security import _hash_token
    execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user["id"], _hash_token(token or "")))
    audit(user, "cambio de contraseña", ip=client_ip(request))
    return {"ok": True}
