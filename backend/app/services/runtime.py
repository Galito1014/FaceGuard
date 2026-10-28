"""Orquestación de los servicios en segundo plano."""
from __future__ import annotations

import logging
import time
from typing import Any

from app.config import config
from app.core import compat
from app.services.camera import camera
from app.services.events import create_event
from app.services.face_engine import engine, gallery
from app.services.gpio import gpio
from app.services.pipeline import pipeline
from app.services.realtime import hub
from app.services.settings_store import settings

log = logging.getLogger("faceguard.runtime")

CAMERA_KEYS = {"camera_index", "camera_width", "camera_height", "demo_mode"}
GPIO_KEYS = {"led_pin", "buzzer_pin"}
_last_camera_event = 0.0


def _on_camera_status(connected: bool, message: str) -> None:
    """Registra conexiones/desconexiones de la cámara (máximo 1 evento cada 30 s)."""
    global _last_camera_event
    hub.publish("camera", camera.status())
    if not camera.running or time.time() - _last_camera_event < 30:
        return
    _last_camera_event = time.time()
    create_event("sistema", config.camera_name, message=message, is_simulated=camera.synthetic)


def start_monitoring() -> None:
    cfg = settings.all()
    camera.start(cfg["camera_index"], cfg["camera_width"], cfg["camera_height"], synthetic=cfg["demo_mode"])
    pipeline.start()
    log.info("Monitoreo iniciado (%s)", "demostración" if cfg["demo_mode"] else compat.camera_label(cfg["camera_index"]))


def stop_monitoring() -> None:
    pipeline.stop()
    camera.stop()
    log.info("Monitoreo detenido")


def restart_engine() -> dict[str, Any]:
    was_running = pipeline.running
    pipeline.stop()
    ok = engine.load()
    gallery.load()
    pipeline.reset_tracking()
    if was_running:
        pipeline.start()
    return {"engine_ready": ok, "gallery_size": gallery.size, "error": engine.error}


def on_settings_changed(changed: dict[str, Any]) -> None:
    keys = set(changed)
    if keys & GPIO_KEYS:
        gpio.setup(settings.get("led_pin"), settings.get("buzzer_pin"))
    if "monitoring_enabled" in keys:
        (start_monitoring if changed["monitoring_enabled"] else stop_monitoring)()
    elif keys & CAMERA_KEYS and settings.get("monitoring_enabled"):
        start_monitoring()
    if "match_threshold" in keys or "confirm_frames" in keys:
        pipeline.reset_tracking()
    hub.publish("settings", settings.all(), perm="settings.view")


def startup() -> None:
    camera.on_status_change = _on_camera_status
    settings.on_change(on_settings_changed)
    engine.load()
    gallery.load()
    gpio.setup(settings.get("led_pin"), settings.get("buzzer_pin"))
    if not config.disable_workers and settings.get("monitoring_enabled"):
        start_monitoring()


def shutdown() -> None:
    stop_monitoring()
    gpio.close()
