"""Tiempo de comparación y memoria según el número de plantillas.

Uso (desde backend/):
  python -m scripts.benchmark_gallery

Usa vectores aleatorios en memoria: no lee la base de datos ni datos reales.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.face_engine import Gallery  # noqa: E402

REPEATS = 2000


def main() -> int:
    rng = np.random.default_rng(1)
    print(f"{'Plantillas':>11} {'ms/comparación':>15} {'Memoria (MB)':>13}")
    for size in (100, 1_000, 10_000, 50_000):
        vectors = rng.normal(size=(size, 128)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        gallery = Gallery()
        gallery._matrix = vectors
        gallery._meta = [{"entry_id": i, "classification": "no_autorizada" if i % 10 else "autorizada"} for i in range(size)]
        gallery._restricted = np.array([m["classification"] == "no_autorizada" for m in gallery._meta])
        probe = vectors[0]
        start = time.perf_counter()
        for _ in range(REPEATS):
            gallery.best_match(probe, 0.42)
        ms = (time.perf_counter() - start) / REPEATS * 1000
        print(f"{size:>11} {ms:>15.3f} {vectors.nbytes / 1024 ** 2:>13.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
