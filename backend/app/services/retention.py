"""Conservación de datos: borrado automático y vencimiento de registros.

Se ejecuta al iniciar y luego cada hora:
  * Elimina eventos más antiguos que `retention_days_events`
    (las alertas aún pendientes de revisión se conservan).
  * Borra de forma segura las capturas más antiguas que `retention_days_snapshots`.
  * Marca como "vencido" todo registro de la lista con fecha de revisión pasada
    y lo excluye del reconocimiento.
  * Elimina sesiones expiradas y auditoría más antigua que `retention_days_audit`.
  * Borra archivos sin referencia en la base de datos, por ejemplo tras un corte
    de luz durante un registro. Se espera una hora para no tocar uno en curso.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import config
from app.core.audit import audit
from app.core.crypto import secure_delete
from app.core.database import get_db, query, utcnow
from app.services.settings_store import settings

log = logging.getLogger("faceguard.retention")

ORPHAN_MIN_AGE_SECONDS = 3600


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def _remove_orphans() -> int:
    referenced = {r["f"] for r in query("SELECT photo_file AS f FROM face_samples")}
    referenced |= {r["f"] for r in query("SELECT snapshot_file AS f FROM events WHERE snapshot_file IS NOT NULL")}
    limit = time.time() - ORPHAN_MIN_AGE_SECONDS
    removed = 0
    for sub in ("photos", "snapshots"):
        folder = config.media_dir / sub
        if not folder.exists():
            continue
        for path in folder.glob("*.bin"):
            name = f"{sub}/{path.name}"
            if name not in referenced and path.stat().st_mtime < limit:
                secure_delete(name)
                removed += 1
    return removed


def run_retention() -> dict[str, Any]:
    cfg = settings.all()
    ev_cut = _cutoff(cfg["retention_days_events"])
    snap_cut = _cutoff(cfg["retention_days_snapshots"])
    old_snaps = query(
        "SELECT id, snapshot_file FROM events WHERE snapshot_file IS NOT NULL AND occurred_at < ? "
        "AND (review_status IS NULL OR review_status != 'pendiente')", (snap_cut,))
    old_events_files = query(
        "SELECT snapshot_file FROM events WHERE occurred_at < ? AND snapshot_file IS NOT NULL "
        "AND (review_status IS NULL OR review_status != 'pendiente')", (ev_cut,))
    for r in old_snaps + old_events_files:
        secure_delete(r["snapshot_file"])
    now = utcnow()
    with get_db() as db:
        if old_snaps:
            db.executemany("UPDATE events SET snapshot_file = NULL WHERE id = ?", [(r["id"],) for r in old_snaps])
        events_deleted = db.execute(
            "DELETE FROM events WHERE occurred_at < ? AND (review_status IS NULL OR review_status != 'pendiente')",
            (ev_cut,)).rowcount
        expired = db.execute(
            "SELECT id, uid FROM persons WHERE status = 'activo' AND expires_at <= ?", (now,)).fetchall()
        for e in expired:
            db.execute("UPDATE persons SET status = 'vencido', updated_at = ? WHERE id = ?", (now, e["id"]))
            db.execute("INSERT INTO person_history (entry_id, username, action, changes, at) VALUES (?,?,?,?,?)",
                       (e["id"], "sistema", "vencido automáticamente", '{"status": ["activo", "vencido"]}', now))
        sessions = db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,)).rowcount
        audit_deleted = db.execute("DELETE FROM audit_log WHERE at < ?", (_cutoff(cfg["retention_days_audit"]),)).rowcount
    result = {"events_deleted": events_deleted, "snapshots_deleted": len(old_snaps) + len(old_events_files),
              "entries_expired": len(expired), "sessions_deleted": sessions, "audit_deleted": audit_deleted,
              "orphans_deleted": _remove_orphans()}
    if any(result.values()):
        log.info("Retención aplicada: %s", result)
        audit(None, "retención automática", details=result)
    if expired:
        from app.services.face_engine import gallery
        gallery.load()
    return result
