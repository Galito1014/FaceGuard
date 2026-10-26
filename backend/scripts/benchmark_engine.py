"""Prueba del motor facial: similitud entre fotografías y tiempo por fotograma.

Uso (desde backend/):
  python -m scripts.benchmark_engine referencia.jpg prueba1.jpg prueba2.jpg ...

Imprime la similitud de cada imagen de prueba contra la referencia y si
superaría el umbral configurado, más el tiempo medio de detección +
reconocimiento. Útil para documentar las pruebas en la Raspberry Pi con
fotos de voluntarios que hayan dado su consentimiento.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.face_engine import engine  # noqa: E402

THRESHOLD = 0.42


def main(paths: list[str]) -> int:
    if len(paths) < 2:
        print(__doc__); return 1
    if not engine.load():
        print(engine.error); return 1
    ref = engine.analyze_photo(Path(paths[0]).read_bytes())
    print(f"Referencia: {paths[0]} · apta={ref['ok']}")
    for c in ref["checks"]:
        print(f"   {'✓' if c['ok'] else '✗'} {c['name']}: {c['detail']}")
    if ref["embedding"] is None:
        return 1
    print(f"\n{'Imagen':<40} {'Rostros':>7} {'Similitud':>10}  Resultado (umbral {THRESHOLD})")
    for p in paths[1:]:
        img = cv2.imread(p)
        faces, small, _ = engine.detect(img, 480, 0.85, 20)
        sims = [float(engine.embed(small, f) @ ref["embedding"]) for f in faces]
        best = max(sims, default=0.0)
        print(f"{Path(p).name:<40} {len(faces):>7} {best:>10.3f}  {'POSIBLE COINCIDENCIA' if best >= THRESHOLD else 'sin coincidencia'}")
    frame = cv2.resize(cv2.imread(paths[0]), (640, 480))
    n, t0 = 30, time.time()
    for _ in range(n):
        faces, small, _ = engine.detect(frame, 480, 0.85, 20)
        for f in faces:
            engine.embed(small, f)
    print(f"\nTiempo medio por fotograma (640×480, detección + reconocimiento): {(time.time() - t0) / n * 1000:.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
