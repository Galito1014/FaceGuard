"""Utilidades compartidas por los routers."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException


def norm_dt(value: str | None) -> str | None:
    """Normaliza una fecha ISO (acepta 'Z' o 'YYYY-MM-DD') a UTC con segundos."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"Fecha inválida: {value}") from None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # hora local del dispositivo
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    return page_size, (page - 1) * page_size
