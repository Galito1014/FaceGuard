"""Creación y serialización de eventos y alertas."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from app.core.database import execute, query_one, utcnow
from app.services.realtime import hub

log = logging.getLogger("faceguard.events")

TYPE_LABELS = {
    "deteccion": "Detección",
    "coincidencia": "Posible coincidencia",
    "captura": "Captura autorizada",
    "sistema": "Sistema",
}
REVIEW_LABELS = {
    "pendiente": "Pendiente de revisión",
    "confirmada": "Coincidencia confirmada",
    "falso_positivo": "Falso positivo",
    "cerrada": "Cerrada",
}


def new_uid(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"


def create_event(
    type_: str,
    camera: str,
    *,
    entry: dict[str, Any] | None = None,
    score: float | None = None,
    level: str | None = None,
    faces_count: int = 0,
    review_status: str | None = None,
    message: str = "",
    snapshot_file: str | None = None,
    is_simulated: bool = False,
    occurred_at: str | None = None,
    notify: bool = True,
) -> dict[str, Any]:
    uid = new_uid("EV")
    eid = execute(
        """INSERT INTO events (uid, occurred_at, camera, type, entry_id, entry_name, score, level, faces_count,
                               review_status, message, snapshot_file, is_simulated)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, occurred_at or utcnow(), camera, type_, entry["entry_id"] if entry else None,
         entry["name"] if entry else None, None if score is None else round(score, 4), level, faces_count,
         review_status, message, snapshot_file, int(is_simulated)),
    )
    row = query_one("SELECT * FROM events WHERE id = ?", (eid,))
    if notify:
        public = serialize_event(row)
        hub.publish("event", public, perm="events.view")
        if type_ == "coincidencia":
            hub.publish("alert", public, perm="alerts.view")
    return row


def serialize_event(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k != "snapshot_file"}
    out["has_snapshot"] = bool(row.get("snapshot_file"))
    out["is_simulated"] = bool(row.get("is_simulated"))
    out["type_label"] = TYPE_LABELS.get(row["type"], row["type"])
    out["review_label"] = REVIEW_LABELS.get(row.get("review_status") or "", None)
    return out
