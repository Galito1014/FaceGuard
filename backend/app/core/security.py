"""Autenticación, sesiones y control de acceso por roles (RBAC)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, WebSocket, status

from app.config import config
from app.core.database import execute, query_one, utcnow

COOKIE_NAME = "fg_session"

# ---------------------------------------------------------------- contraseñas
# scrypt (biblioteca estándar) — resistente a ataques por GPU, sin dependencias nativas.
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "La contraseña debe tener al menos 10 caracteres."
    if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        return "La contraseña debe combinar letras y números."
    return None


# ------------------------------------------------- límite de intentos de login
class LoginThrottle:
    """Bloquea 5 minutos tras 5 intentos fallidos por usuario+IP."""

    MAX_ATTEMPTS = 5
    WINDOW = 300

    def __init__(self) -> None:
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _key(self, username: str, ip: str) -> str:
        return f"{username.lower()}|{ip}"

    def is_blocked(self, username: str, ip: str) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._fails.get(self._key(username, ip), []) if now - t < self.WINDOW]
            self._fails[self._key(username, ip)] = hits
            return len(hits) >= self.MAX_ATTEMPTS

    def fail(self, username: str, ip: str) -> None:
        with self._lock:
            self._fails.setdefault(self._key(username, ip), []).append(time.time())

    def reset(self, username: str, ip: str) -> None:
        with self._lock:
            self._fails.pop(self._key(username, ip), None)


throttle = LoginThrottle()


# ------------------------------------------------------------------- sesiones
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=config.session_hours)
    execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, ip, user_agent) VALUES (?,?,?,?,?,?)",
        (_hash_token(token), user_id, utcnow(), expires.replace(microsecond=0).isoformat(), ip, (user_agent or "")[:200]),
    )
    return token


def destroy_session(token: str | None) -> None:
    if token:
        execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


def user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    row = query_one(
        """SELECT u.id, u.username, u.full_name, u.role, u.active, u.must_change_password, s.expires_at
           FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?""",
        (_hash_token(token),),
    )
    if not row or not row["active"]:
        return None
    if row["expires_at"] < utcnow():
        destroy_session(token)
        return None
    row.pop("expires_at")
    return row


# ---------------------------------------------------------------------- RBAC
ROLES = ("superadmin", "admin", "operator", "auditor")
ROLE_LABELS = {
    "superadmin": "Superadministrador",
    "admin": "Administrador",
    "operator": "Operador",
    "auditor": "Auditor",
}

# Permiso -> roles autorizados.
PERMISSIONS: dict[str, set[str]] = {
    "dashboard.view":     {"superadmin", "admin", "operator", "auditor"},
    "camera.view":        {"superadmin", "admin", "operator"},
    "camera.control":     {"superadmin", "admin", "operator"},
    "camera.capture":     {"superadmin", "admin", "operator"},
    "blacklist.view":     {"superadmin", "admin", "auditor"},
    "blacklist.photos":   {"superadmin", "admin"},
    "blacklist.edit":     {"superadmin", "admin"},
    "alerts.view":        {"superadmin", "admin", "operator", "auditor"},
    "alerts.images":      {"superadmin", "admin", "operator"},
    "alerts.review":      {"superadmin", "admin", "operator"},
    "events.view":        {"superadmin", "admin", "operator", "auditor"},
    "events.export":      {"superadmin", "admin", "auditor"},
    "users.manage":       {"superadmin"},
    "audit.view":         {"superadmin", "auditor"},
    "settings.view":      {"superadmin", "admin"},
    "settings.edit":      {"superadmin"},
    "system.control":     {"superadmin"},
    "demo.control":       {"superadmin", "admin"},
}


def has_perm(user: dict[str, Any], perm: str) -> bool:
    return user["role"] in PERMISSIONS.get(perm, set())


def permissions_for(role: str) -> list[str]:
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def current_user(request: Request) -> dict[str, Any]:
    user = user_from_token(request.cookies.get(COOKIE_NAME))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no válida o expirada.")
    return user


def require(perm: str) -> Callable[..., dict[str, Any]]:
    """Dependencia FastAPI: exige el permiso indicado.

    Los usuarios que aún deben cambiar su contraseña inicial solo pueden
    acceder a /api/auth/*.
    """

    def dep(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["must_change_password"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Debe cambiar su contraseña antes de continuar.")
        if not has_perm(user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permisos para esta acción.")
        return user

    return dep


def ws_user(ws: WebSocket) -> dict[str, Any] | None:
    user = user_from_token(ws.cookies.get(COOKIE_NAME))
    if user and not user["must_change_password"]:
        return user
    return None
