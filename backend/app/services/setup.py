"""Configuración inicial (asistente de primer uso).

Mientras no exista ningún usuario, FaceGuard AI está "sin configurar" y el panel
muestra el asistente. Para que nadie más en la red local pueda adelantarse y
crear la cuenta administradora en una Raspberry Pi, el asistente pide un
**código de configuración** cuando la petición no viene del propio equipo. El
código se genera al arrancar y se guarda en <datos>/secret/setup_code.txt (el
instalador de la Pi lo muestra en pantalla). En FaceGuard AI Desktop el panel
siempre se abre desde el propio equipo, así que no hace falta el código.
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import threading
import time

from app.config import config
from app.core.database import query_one

log = logging.getLogger("faceguard.setup")

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I
_lock = threading.Lock()
_failures: list[float] = []
MAX_FAILURES = 10
FAILURE_WINDOW = 300


def code_path():
    return config.secret_dir / "setup_code.txt"


def needs_setup() -> bool:
    return query_one("SELECT id FROM users LIMIT 1") is None


def ensure_setup_code() -> str:
    """Crea (o reutiliza) el código de configuración y lo deja en un archivo protegido."""
    path = code_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) == 8:
            return existing
    except OSError:
        pass
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    path.write_text(code + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    log.warning("FaceGuard AI no está configurado. Código de configuración inicial: %s (también en %s)", code, path)
    return code


def check_code(candidate: str | None) -> bool:
    now = time.monotonic()
    with _lock:
        _failures[:] = [t for t in _failures if now - t < FAILURE_WINDOW]
        if len(_failures) >= MAX_FAILURES:
            return False
    expected = ensure_setup_code()
    ok = bool(candidate) and hmac.compare_digest(candidate.strip().upper().replace("-", "").replace(" ", ""), expected)
    if not ok:
        with _lock:
            _failures.append(now)
    return ok


def blocked() -> bool:
    now = time.monotonic()
    with _lock:
        return len([t for t in _failures if now - t < FAILURE_WINDOW]) >= MAX_FAILURES


def finish() -> None:
    try:
        code_path().unlink()
    except OSError:
        pass
    with _lock:
        _failures.clear()


# Evita que dos asistentes abiertos a la vez creen dos administradores.
creation_lock = threading.Lock()
