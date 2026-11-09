"""Configuración modificable en tiempo de ejecución, persistida en SQLite."""
from __future__ import annotations

import json
import threading
from typing import Any, Callable

from app.core import compat
from app.core.database import get_db, query

DEFAULTS: dict[str, Any] = {
    # Reconocimiento
    "match_threshold": 0.42,         # similitud coseno SFace (≥ 0.363 recomendado por OpenCV)
    "detection_confidence": 0.85,    # confianza mínima YuNet
    "min_face_size": 60,             # píxeles en la imagen procesada
    "confirm_frames": 3,             # fotogramas consecutivos para confirmar coincidencia
    "process_interval_ms": 250,      # frecuencia de procesamiento (4 fps)
    # Ancho de la imagen que se analiza. En la Raspberry Pi, 320: YuNet tarda
    # aproximadamente la mitad que con 480 (el tamaño mínimo de rostro se mide
    # en la imagen original, así que no cambia).
    "process_width": 320 if compat.IS_LOW_POWER else 480,
    "recheck_interval_ms": 1000,     # revisión periódica de cada rostro (0 = en cada ciclo)
    "dedup_seconds": 15,             # cooldown por persona: sin alertas ni alarmas repetidas
    "detection_log_seconds": 30,     # agrupa detecciones sin coincidencia
    # Cámara
    "camera_index": 0,
    "camera_width": 640,
    "camera_height": 480,
    "monitoring_enabled": True,
    # Alertas y GPIO
    "alerts_enabled": True,
    "alert_sound": True,             # aviso sonoro en el panel
    "gpio_enabled": True,
    "led_pin": 17,
    "buzzer_pin": 27,
    "led_enabled": True,
    "buzzer_enabled": True,
    "buzzer_min_level": "bajo",      # bajo | medio | alto (bajo = suena con toda coincidencia)
    "led_seconds": 5,                # tiempo que el LED queda encendido
    "buzzer_seconds": 3,             # tiempo que suena el buzzer
    "buzzer_type": "activo",         # activo (oscilador interno) | pasivo (necesita PWM)
    "buzzer_pattern": "intermitente",  # intermitente | continuo
    "buzzer_frequency": 2500,        # Hz, solo para buzzer pasivo
    # Retención (días)
    "retention_days_events": 30,
    "retention_days_snapshots": 15,
    "retention_days_audit": 365,
    "retention_days_expired_authorized": 30,  # días tras vencer antes de borrar su biometría
    # Demostración
    "demo_mode": False,
}

# Validación: clave -> (tipo, mínimo, máximo) o conjunto de opciones válidas.
RULES: dict[str, Any] = {
    "match_threshold": (float, 0.25, 0.9),
    "detection_confidence": (float, 0.5, 0.99),
    "min_face_size": (int, 20, 400),
    "confirm_frames": (int, 1, 10),
    "process_interval_ms": (int, 100, 5000),
    "process_width": (int, 240, 1280),
    "recheck_interval_ms": (int, 0, 10000),
    "dedup_seconds": (int, 5, 3600),
    "detection_log_seconds": (int, 5, 3600),
    "camera_index": (int, 0, 9),
    "camera_width": (int, 160, 1920),
    "camera_height": (int, 120, 1080),
    "monitoring_enabled": (bool,),
    "alerts_enabled": (bool,),
    "alert_sound": (bool,),
    "gpio_enabled": (bool,),
    "led_pin": "gpio_pin",
    "buzzer_pin": "gpio_pin",
    "led_enabled": (bool,),
    "buzzer_enabled": (bool,),
    "buzzer_min_level": {"bajo", "medio", "alto"},
    "led_seconds": (int, 1, 60),
    "buzzer_seconds": (int, 1, 60),
    "buzzer_type": {"activo", "pasivo"},
    "buzzer_pattern": {"intermitente", "continuo"},
    "buzzer_frequency": (int, 200, 8000),
    "retention_days_events": (int, 1, 3650),
    "retention_days_snapshots": (int, 1, 3650),
    "retention_days_audit": (int, 30, 3650),
    "retention_days_expired_authorized": (int, 1, 3650),
    "demo_mode": (bool,),
}


class SettingsStore:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = dict(DEFAULTS)
        self._lock = threading.Lock()
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def load(self) -> None:
        rows = query("SELECT key, value FROM settings")
        with self._lock:
            self._cache = dict(DEFAULTS)
            for r in rows:
                if r["key"] in DEFAULTS:
                    self._cache[r["key"]] = json.loads(r["value"])

    def get(self, key: str) -> Any:
        with self._lock:
            return self._cache[key]

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._cache)

    @staticmethod
    def validate(key: str, value: Any) -> Any:
        if key not in RULES:
            raise ValueError(f"Parámetro desconocido: {key}")
        rule = RULES[key]
        if rule == "gpio_pin":
            from app.services.alarm_controller import SAFE_PINS, physical_pin
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key}: tipo inválido") from None
            if value not in SAFE_PINS:
                raise ValueError(f"{key}: GPIO{value} no está permitido. Use uno libre de I2C/UART/SPI: "
                                 + ", ".join(f"GPIO{p} (pin {physical_pin(p)})" for p in sorted(SAFE_PINS)))
            return value
        if isinstance(rule, set):
            if value not in rule:
                raise ValueError(f"{key}: valor no permitido")
            return value
        typ = rule[0]
        if typ is bool:
            if not isinstance(value, bool):
                raise ValueError(f"{key}: debe ser verdadero/falso")
            return value
        try:
            value = typ(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: tipo inválido") from None
        if not rule[1] <= value <= rule[2]:
            raise ValueError(f"{key}: debe estar entre {rule[1]} y {rule[2]}")
        return value

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        clean = {k: self.validate(k, v) for k, v in changes.items()}
        if "led_pin" in clean or "buzzer_pin" in clean:
            led = clean.get("led_pin", self.get("led_pin"))
            buz = clean.get("buzzer_pin", self.get("buzzer_pin"))
            if led == buz:
                raise ValueError("El LED y el buzzer no pueden usar el mismo pin GPIO.")
        with get_db() as db:
            for k, v in clean.items():
                db.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (k, json.dumps(v)))
        with self._lock:
            old = dict(self._cache)
            self._cache.update(clean)
        changed = {k: v for k, v in clean.items() if old.get(k) != v}
        if changed:
            for fn in self._listeners:
                fn(changed)
        return changed

    def on_change(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(fn)


settings = SettingsStore()
