"""Inicia FaceGuard AI en cualquier sistema (Windows 10/11, Raspberry Pi OS, Linux).

Uso (desde la carpeta backend/, con el entorno virtual activado):
  python -m scripts.run                  # usa FACEGUARD_HOST / FACEGUARD_PORT (.env)
  python -m scripts.run --host 0.0.0.0 --port 8000

Lee la configuración de backend/.env (si existe) y de las variables de entorno.
Equivale a: uvicorn app.main:app --host <host> --port <puerto> --workers 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import config  # noqa: E402  (carga backend/.env)
from app.core import compat  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Inicia FaceGuard AI")
    parser.add_argument("--host", default=config.host, help=f"Interfaz de red (actual: {config.host})")
    parser.add_argument("--port", type=int, default=config.port, help=f"Puerto (actual: {config.port})")
    args = parser.parse_args(argv)

    import uvicorn

    print(f"FaceGuard AI · sistema: {compat.os_name()} · datos: {config.data_dir}")
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"Abra http://{shown}:{args.port} en el navegador (Ctrl+C para detener)")
    uvicorn.run("app.main:app", host=args.host, port=args.port, workers=1, app_dir=str(BACKEND))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
