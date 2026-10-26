"""Configuración estática de FaceGuard AI.

Los valores se leen de variables de entorno (o de /etc/faceguard/faceguard.env
cuando se ejecuta como servicio systemd). La configuración que cambia en tiempo
de ejecución (umbral, cámara, LED, etc.) vive en la tabla `settings` de SQLite
y se gestiona en app/services/settings_store.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Config:
    app_name: str = "FaceGuard AI"
    version: str = "1.0.0"
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("FACEGUARD_DATA_DIR", BASE_DIR / "data")))
    models_dir: Path = field(default_factory=lambda: Path(os.getenv("FACEGUARD_MODELS_DIR", BASE_DIR / "models")))
    frontend_dist: Path = field(
        default_factory=lambda: Path(os.getenv("FACEGUARD_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
    )
    # Cookie "Secure" solo si se sirve por HTTPS.
    secure_cookies: bool = field(default_factory=lambda: _env_bool("FACEGUARD_SECURE_COOKIES", False))
    session_hours: int = field(default_factory=lambda: int(os.getenv("FACEGUARD_SESSION_HOURS", "8")))
    # Desactiva hilos de cámara/procesamiento (útil para pruebas automáticas).
    disable_workers: bool = field(default_factory=lambda: _env_bool("FACEGUARD_DISABLE_WORKERS", False))
    initial_admin_password: str | None = field(default_factory=lambda: os.getenv("FACEGUARD_ADMIN_PASSWORD"))
    camera_name: str = field(default_factory=lambda: os.getenv("FACEGUARD_CAMERA_NAME", "CAM-01 Entrada principal"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "faceguard.db"

    @property
    def secret_dir(self) -> Path:
        return self.data_dir / "secret"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def detector_model(self) -> Path:
        return self.models_dir / "face_detection_yunet_2023mar.onnx"

    @property
    def recognizer_model(self) -> Path:
        return self.models_dir / "face_recognition_sface_2021dec.onnx"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.secret_dir, self.media_dir, self.log_dir,
                  self.media_dir / "photos", self.media_dir / "snapshots"):
            d.mkdir(parents=True, exist_ok=True)
        for d in (self.data_dir, self.secret_dir, self.media_dir):
            try:
                os.chmod(d, 0o700)  # solo el usuario del servicio puede leer los datos
            except OSError:
                pass


config = Config()
