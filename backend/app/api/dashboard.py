from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.core.database import query, query_one
from app.core.security import require
from app.services import system_monitor
from app.services.camera import camera
from app.services.events import serialize_event
from app.services.gpio import gpio
from app.services.pipeline import pipeline
from app.services.settings_store import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _local_midnight_utc() -> str:
    local_now = datetime.now().astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).isoformat()


def live_status() -> dict:
    """Estado en vivo (también se envía por WebSocket cada 2 s)."""
    pending = query_one("SELECT COUNT(*) AS n FROM events WHERE type='coincidencia' AND review_status='pendiente'")["n"]
    return {
        "system": system_monitor.snapshot(),
        "camera": camera.status(),
        "engine": pipeline.status(),
        "gpio": gpio.status(),
        "pending_alerts": pending,
        "demo_mode": settings.get("demo_mode"),
    }


@router.get("/summary")
def summary(user: dict = Depends(require("dashboard.view"))):
    today = _local_midnight_utc()
    counts = query_one(
        """SELECT
             (SELECT COUNT(*) FROM persons WHERE classification='no_autorizada' AND status='activo') AS blacklist_active,
             (SELECT COUNT(*) FROM persons WHERE classification='no_autorizada') AS blacklist_total,
             (SELECT COUNT(*) FROM persons) AS persons_total,
             (SELECT COUNT(*) FROM persons WHERE classification='autorizada' AND status='activo') AS authorized_active,
             (SELECT COUNT(*) FROM events WHERE occurred_at >= :t) AS events_today,
             (SELECT COALESCE(SUM(faces_count),0) FROM events WHERE type='deteccion' AND occurred_at >= :t) AS faces_today,
             (SELECT COUNT(*) FROM events WHERE type='coincidencia' AND occurred_at >= :t) AS alerts_today,
             (SELECT COUNT(*) FROM events WHERE type='coincidencia' AND review_status='falso_positivo') AS false_positives,
             (SELECT COUNT(*) FROM events WHERE type='coincidencia' AND review_status='confirmada') AS confirmed""",
        {"t": today},
    )
    recent = query("SELECT * FROM events WHERE type IN ('deteccion','coincidencia','captura') ORDER BY occurred_at DESC LIMIT 8")
    return {**counts, **live_status(), "recent": [serialize_event(r) for r in recent]}


@router.get("/activity")
def activity(period: str = Query("day", alias="range", pattern="^(day|week)$"), user: dict = Depends(require("dashboard.view"))):
    now = datetime.now().astimezone()
    buckets: "OrderedDict[str, dict]" = OrderedDict()
    if period == "day":
        start = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        for i in range(24):
            t = start + timedelta(hours=i)
            buckets[t.strftime("%Y-%m-%d %H")] = {"label": t.strftime("%H:00"), "detecciones": 0, "rostros": 0, "alertas": 0}
        fmt = "%Y-%m-%d %H"
    else:
        start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for i in range(7):
            t = start + timedelta(days=i)
            buckets[t.strftime("%Y-%m-%d")] = {"label": f"{days[t.weekday()]} {t.day}", "detecciones": 0, "rostros": 0, "alertas": 0}
        fmt = "%Y-%m-%d"
    rows = query("SELECT occurred_at, type, faces_count FROM events WHERE occurred_at >= ? AND type IN ('deteccion','coincidencia')",
                 (start.astimezone(timezone.utc).isoformat(),))
    for r in rows:
        key = datetime.fromisoformat(r["occurred_at"]).astimezone().strftime(fmt)
        b = buckets.get(key)
        if not b:
            continue
        if r["type"] == "deteccion":
            b["detecciones"] += 1
            b["rostros"] += r["faces_count"] or 0
        else:
            b["alertas"] += 1
    levels = query("SELECT COALESCE(level,'n/d') AS level, COUNT(*) AS n FROM events WHERE type='coincidencia' AND occurred_at >= ? GROUP BY level",
                   (start.astimezone(timezone.utc).isoformat(),))
    review = query("SELECT review_status AS status, COUNT(*) AS n FROM events WHERE type='coincidencia' AND occurred_at >= ? GROUP BY review_status",
                   (start.astimezone(timezone.utc).isoformat(),))
    return {"range": period, "series": list(buckets.values()), "by_level": levels, "by_review": review}
