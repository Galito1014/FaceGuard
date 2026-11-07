"""Comprobación de nuevas versiones en GitHub Releases.

Es opcional y viene desactivada: solo se consulta Internet si el administrador
activa "Buscar actualizaciones" (asistente o Configuración). La consulta pide la
última versión publicada a la API pública de GitHub y no envía imágenes, datos
biométricos ni datos de la instalación. FaceGuard AI nunca se actualiza solo:
muestra el aviso y el enlace, y la persona decide cuándo instalar.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.request
from typing import Any

from app.config import config

log = logging.getLogger("faceguard.updates")

CACHE_SECONDS = 6 * 3600
_cache: dict[str, Any] = {}
_lock = threading.Lock()


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Las etiquetas previas (-beta) cuentan como la versión base."""
    nums = re.findall(r"\d+", (text or "").split("-", 1)[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _fetch_latest(repo: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"FaceGuard-AI/{config.version}"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 (URL fija de GitHub)
        data = json.loads(resp.read().decode("utf-8"))
    return {"tag": data.get("tag_name", ""), "name": data.get("name") or data.get("tag_name", ""),
            "url": data.get("html_url", f"https://github.com/{repo}/releases"),
            "published_at": data.get("published_at")}


def check(force: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"current": config.version, "edition": config.edition, "latest": None,
                              "update_available": False, "url": f"https://github.com/{config.update_repo}/releases",
                              "error": None}
    with _lock:
        cached = _cache.get("data")
        if cached and not force and time.time() - _cache.get("at", 0) < CACHE_SECONDS:
            latest = cached
        else:
            try:
                latest = _fetch_latest(config.update_repo)
                _cache.update(data=latest, at=time.time())
            except Exception as exc:  # sin Internet, repositorio privado, límite de la API…
                log.info("No se pudo comprobar actualizaciones: %s", exc)
                result["error"] = "No se pudo consultar GitHub. Compruebe la conexión a Internet."
                return result
    result.update(latest=latest["tag"], url=latest["url"], published_at=latest.get("published_at"),
                  update_available=is_newer(latest["tag"], config.version))
    return result
