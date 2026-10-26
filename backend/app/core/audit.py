"""Registro de actividad administrativa (auditoría)."""
from __future__ import annotations

import json
from typing import Any

from app.core.database import execute, utcnow


def audit(user: dict[str, Any] | None, action: str, target: str = "", details: Any = "", ip: str | None = None) -> None:
    if not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    execute(
        "INSERT INTO audit_log (at, user_id, username, action, target, details, ip) VALUES (?,?,?,?,?,?,?)",
        (utcnow(), user["id"] if user else None, user["username"] if user else "sistema", action, target, details, ip),
    )
