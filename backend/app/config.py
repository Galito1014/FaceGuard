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


def load_env_file(path: Path | None = None) -> None:
    """Carga variables FACEGUARD_* desde un archivo .env (si existe).

    Por defecto lee backend/.env (o la ruta de FACEGUARD_ENV_FILE). Es útil en
    Windows y en ejecuciones manuales; en la Raspberry Pi el servicio systemd
    usa /etc/faceguard/faceguard.env. Nunca reemplaza una variable que ya esté
    definida en el entorno, así que no cambia el comportamiento del servicio.
    """
    path = path or Path(os.getenv("FACEGUARD_ENV_FILE", BASE_DIR / ".env"))
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_env_file()


def _env_path(name: str, default: Path) -> Path:
    """Ruta desde una variable de entorno; admite ~, $VAR y %VAR% (Windows)."""
    value = os.getenv(name)
    if not value:
        return Path(default)
    return Path(os.path.expandvars(os.path.expanduser(value)))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Config:
    app_name: str = "FaceGuard AI"
    version: str = "1.0.0"
    data_dir: Path = field(default_factory=lambda: _env_path("FACEGUARD_DATA_DIR", BASE_DIR / "data"))
    models_dir: Path = field(default_factory=lambda: _env_path("FACEGUARD_MODELS_DIR", BASE_DIR / "models"))
    frontend_dist: Path = field(
        default_factory=lambda: _env_path("FACEGUARD_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist")
    )
    host: str = field(default_factory=lambda: os.getenv("FACEGUARD_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("FACEGUARD_PORT", "8000")))
    # Cookie "Secure" solo si se sirve por HTTPS.
    secure_cookies: bool = field(default_factory=lambda: _env_bool("FACEGUARD_SECURE_COOKIES", False))
    session_hours: int = field(default_factory=lambda: int(os.getenv("FACEGUARD_SESSION_HOURS", "8")))
    # Desactiva hilos de cámara/procesamiento (útil para pruebas automáticas).
    disable_workers: bool = field(default_factory=lambda: _env_bool("FACEGUARD_DISABLE_WORKERS", False))
    initial_admin_password: str | None = field(default_factory=lambda: os.getenv("FACEGUARD_ADMIN_PASSWORD"))
    # Intentos de inicio de sesión: 0 = ilimitados, sin espera.
    login_max_attempts: int = field(default_factory=lambda: int(os.getenv("FACEGUARD_LOGIN_MAX_ATTEMPTS", "0")))
    login_lock_seconds: int = field(default_factory=lambda: int(os.getenv("FACEGUARD_LOGIN_LOCK_SECONDS", "300")))
    # 0 = el admin inicial entra directo con FACEGUARD_ADMIN_PASSWORD, sin cambio obligatorio.
    force_password_change: bool = field(default_factory=lambda: _env_bool("FACEGUARD_FORCE_PASSWORD_CHANGE", True))
    camera_name: str = field(default_factory=lambda: os.getenv("FACEGUARD_CAMERA_NAME", "CAM-01 Entrada principal"))
    # Por defecto, la base de datos y las imágenes viven dentro de data_dir.
    db_override: str = field(default_factory=lambda: os.getenv("FACEGUARD_DB_PATH", ""))
    media_override: str = field(default_factory=lambda: os.getenv("FACEGUARD_MEDIA_DIR", ""))
    log_level: str = field(default_factory=lambda: os.getenv("FACEGUARD_LOG_LEVEL", "INFO").upper())

    @property
    def db_path(self) -> Path:
        return _env_path("FACEGUARD_DB_PATH", self.data_dir / "faceguard.db") if self.db_override else self.data_dir / "faceguard.db"

    @property
    def secret_dir(self) -> Path:
        return self.data_dir / "secret"

    @property
    def media_dir(self) -> Path:
        return _env_path("FACEGUARD_MEDIA_DIR", self.data_dir / "media") if self.media_override else self.data_dir / "media"

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
                # Linux: solo el usuario del servicio puede leer los datos.
                # Windows: chmod no aplica ACL; la carpeta queda protegida por
                # los permisos NTFS del perfil del usuario.
                os.chmod(d, 0o700)
            except OSError:
                pass


config = Config()
