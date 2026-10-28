"""Descarga los modelos de OpenCV Zoo (Apache 2.0) y verifica su integridad.

Versión multiplataforma de scripts/download_models.sh (sirve en Windows,
donde no hay bash ni sha256sum). Mismos archivos, misma URL y mismas sumas.

Uso (desde backend/):  python -m scripts.download_models
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import config  # noqa: E402  (respeta FACEGUARD_MODELS_DIR)

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
FILES = {
    "face_detection_yunet_2023mar.onnx":
        ("face_detection_yunet", "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx":
        ("face_recognition_sface", "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    target = config.models_dir
    target.mkdir(parents=True, exist_ok=True)
    for name, (folder, digest) in FILES.items():
        path = target / name
        if path.exists() and sha256(path) == digest:
            print(f"OK  {name} ya existe")
            continue
        url = f"{BASE}/{folder}/{name}"
        print(f"..  Descargando {name}")
        tmp = path.with_suffix(".part")
        last_error: Exception | None = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
                    while chunk := resp.read(1 << 20):
                        out.write(chunk)
                last_error = None
                break
            except OSError as exc:
                last_error = exc
        if last_error is not None:
            tmp.unlink(missing_ok=True)
            print(f"ERR No se pudo descargar {name}: {last_error}")
            return 1
        if sha256(tmp) != digest:
            tmp.unlink(missing_ok=True)
            print(f"ERR Suma de verificación incorrecta para {name}")
            return 1
        tmp.replace(path)
        print(f"OK  {name}")
    print(f"Modelos listos en {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
