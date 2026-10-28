"""Detección del sistema operativo y diferencias entre plataformas.

FaceGuard AI usa una sola base de código para Raspberry Pi OS (Linux ARM64) y
Windows 10/11. Este módulo concentra lo que cambia entre ellas:

* qué backend de OpenCV se usa para abrir la cámara USB / webcam
  (V4L2 en Linux; DirectShow o Media Foundation en Windows),
* cómo se nombra cada cámara en la interfaz (/dev/videoN o "Cámara N"),
* si tiene sentido intentar usar los pines GPIO (solo en Linux).

El backend de la cámara se puede forzar con la variable de entorno
FACEGUARD_CAMERA_BACKEND = auto | v4l2 | dshow | msmf | avfoundation | any.
"""
from __future__ import annotations

import os
import platform
import sys

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"


def os_name() -> str:
    """Nombre corto del sistema operativo: windows, linux, macos u otro."""
    if IS_WINDOWS:
        return "windows"
    if IS_LINUX:
        return "linux"
    if IS_MACOS:
        return "macos"
    return platform.system().lower() or "otro"


# Backends de captura de OpenCV, por nombre (se resuelven al usarlos para no
# importar cv2 desde aquí).
_BACKEND_ATTRS = {
    "v4l2": "CAP_V4L2",
    "dshow": "CAP_DSHOW",
    "msmf": "CAP_MSMF",
    "avfoundation": "CAP_AVFOUNDATION",
    "any": "CAP_ANY",
}

# Orden por defecto en cada sistema. En Windows se prueba primero DirectShow
# porque abre las webcams USB más rápido y respeta el formato MJPG; si falla se
# usa Media Foundation.
_DEFAULT_ORDER = {
    "linux": ["v4l2"],  # igual que la versión original para Raspberry Pi
    "windows": ["dshow", "msmf", "any"],
    "macos": ["avfoundation", "any"],
}


def camera_backend_names() -> list[str]:
    """Backends a probar, en orden, según el sistema y FACEGUARD_CAMERA_BACKEND."""
    forced = os.getenv("FACEGUARD_CAMERA_BACKEND", "auto").strip().lower()
    if forced in _BACKEND_ATTRS:
        return [forced]
    return list(_DEFAULT_ORDER.get(os_name(), ["any"]))


def camera_backends(cv2_module) -> list[tuple[str, int]]:
    """Lista de (nombre, constante de OpenCV) disponibles en esta instalación."""
    result = []
    for name in camera_backend_names():
        value = getattr(cv2_module, _BACKEND_ATTRS[name], None)
        if value is not None:
            result.append((name, int(value)))
    return result or [("any", 0)]


def camera_prefix() -> str:
    """Prefijo con el que se muestra el índice de la cámara en la interfaz."""
    return "/dev/video" if IS_LINUX else "Cámara "


def camera_label(index: int) -> str:
    return f"{camera_prefix()}{index}"


def gpio_supported() -> bool:
    """Los pines GPIO (gpiozero) solo existen en Linux (Raspberry Pi)."""
    return IS_LINUX
