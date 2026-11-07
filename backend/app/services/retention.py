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
from app.services.persons import delete_files
from app.services.settings_store import settings

log = logging.getLogger("faceguard.retention")

ORPHAN_MIN_AGE_SECONDS = 3600
ORPHAN_SAFE_COUNT = 5  # hasta aquí se borra aunque superen a los archivos registrados


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()


def _remove_orphans() -> int:
    """Borra archivos sin referencia, solo si la base de datos parece la correcta.

    Una base vacía o equivocada haría parecer sobrantes todos los archivos, y este
    borrado no se puede deshacer. Ante esa duda no se borra nada.
    """
    referenced = {r["f"] for r in query("SELECT photo_file AS f FROM face_samples")}
    referenced |= {r["f"] for r in query("SELECT snapshot_file AS f FROM events WHERE snapshot_file IS NOT NULL")}
    limit = time.time() - ORPHAN_MIN_AGE_SECONDS
    orphans = []
    for sub in ("photos", "snapshots"):
        folder = config.media_dir / sub
        if not folder.exists():
            continue
        for path in folder.glob("*.bin"):
            name = f"{sub}/{path.name}"
            if name not in referenced and path.stat().st_mtime < limit:
                orphans.append(name)
    if not orphans:
        return 0
    if not referenced or len(orphans) > max(ORPHAN_SAFE_COUNT, len(referenced)):
        log.warning("Limpieza omitida: %d archivos sin referencia frente a %d registrados. Revise que la base de datos sea la correcta.",
                    len(orphans), len(referenced))
        return 0
    delete_files(orphans)
    return len(orphans)


def _purge_expired_authorized(days: int) -> int:
    """Borra a las personas autorizadas vencidas: su consentimiento ya no está vigente."""
    cutoff = _cutoff(days)
    rows = query("SELECT id, uid FROM persons WHERE classification = 'autorizada' AND expires_at < ?", (cutoff,))
    if not rows:
        return 0
    ids = [(r["id"],) for r in rows]
    files = [r["photo_file"] for r in query(
        """SELECT s.photo_file FROM face_samples s JOIN persons p ON p.id = s.person_id
           WHERE p.classification = 'autorizada' AND p.expires_at < ?""", (cutoff,))]
    with get_db() as db:
        db.executemany("DELETE FROM persons WHERE id = ?", ids)
    delete_files(files)
    audit(None, "borrado de personas autorizadas vencidas", details=[r["uid"] for r in rows])
    return len(rows)


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
        # El historial de la alarma física sigue el mismo plazo que los eventos.
        alarm_deleted = db.execute("DELETE FROM alarm_activations WHERE at < ? AND state != 'activa'", (ev_cut,)).rowcount
    purged = _purge_expired_authorized(cfg["retention_days_expired_authorized"])
    if expired or purged:
        from app.services.face_engine import gallery
        gallery.load()
    try:
        orphans = _remove_orphans()
    except Exception:
        log.exception("No se pudo completar la limpieza de archivos")
        orphans = 0
    result = {"events_deleted": events_deleted, "snapshots_deleted": len(old_snaps) + len(old_events_files),
              "entries_expired": len(expired), "sessions_deleted": sessions, "audit_deleted": audit_deleted,
              "authorized_purged": purged, "orphans_deleted": orphans, "alarm_activations_deleted": alarm_deleted}
    if any(result.values()):
        log.info("Retención aplicada: %s", result)
        audit(None, "retención automática", details=result)
    return result
