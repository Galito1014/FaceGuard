"""Prueba del motor facial: similitud entre fotografías y tiempo por fotograma.

Uso (desde backend/):
  python -m scripts.benchmark_engine referencia.jpg prueba1.jpg prueba2.jpg ...

Imprime la similitud de cada imagen de prueba contra la referencia y si
superaría el umbral configurado, más el tiempo medio de detección +
reconocimiento. Útil para documentar las pruebas en la Raspberry Pi con
fotos de voluntarios que hayan dado su consentimiento.

Para comparar el procesamiento con y sin seguimiento de rostros:
  python -m scripts.benchmark_engine --video ruta.mp4 referencia.jpg

Procesa el video dos veces, a 4 análisis por segundo de video, e imprime las
llamadas a SFace, el tiempo y los fotogramas confirmados de cada pasada.
Use un video corto (unos 30 segundos): los fotogramas se guardan en memoria.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.face_engine import engine  # noqa: E402
from app.services.tracker import FaceTracker  # noqa: E402

THRESHOLD = 0.42
CONFIRM_FRAMES = 2
VIDEO_STEP_SECONDS = 0.25


def simulate(detections, recheck_s, threshold, confirm_frames, embed_fn) -> dict:
    """Aplica el seguimiento a detecciones ya calculadas, con el reloj del video.

    `detections` es una lista de (tiempo_video, [cajas]). `embed_fn(ciclo, rostro)`
    devuelve (meta, similitud).
    """
    tracker = FaceTracker()
    result = {"embeds": 0, "skipped": 0, "confirmed_frames": 0}
    for cycle, (now, boxes) in enumerate(detections):
        any_confirmed = False
        for index, track in enumerate(tracker.update(boxes, now)):
            if tracker.needs_embedding(track, now, recheck_s):
                meta, sim = embed_fn(cycle, index)
                tracker.record_result(track, meta, sim, threshold, confirm_frames, now)
                result["embeds"] += 1
            else:
                result["skipped"] += 1
            any_confirmed = any_confirmed or track.confirmed
        result["confirmed_frames"] += int(any_confirmed)
    return result


def run_video(video_path: str, reference_path: str) -> int:
    if not engine.load():
        print(engine.error); return 1
    ref = engine.analyze_photo(Path(reference_path).read_bytes())
    if ref["embedding"] is None:
        print(f"La referencia {reference_path} no es apta."); return 1
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"No se pudo abrir el video: {video_path}"); return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * VIDEO_STEP_SECONDS))
    cycles, index = [], 0
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step == 0:
            faces, small, _ = engine.detect(frame, 480, 0.85, 20)
            cycles.append((index / fps, faces, small))
        index += 1
    cap.release()
    detect_s = time.time() - t0
    if not cycles:
        print(f"El video no tiene fotogramas: {video_path}"); return 1

    def embed_fn(cycle: int, i: int):
        _, faces, small = cycles[cycle]
        return {"entry_id": 1}, float(engine.embed(small, faces[i]) @ ref["embedding"])

    detections = [(t, [f.box for f in faces]) for t, faces, _ in cycles]
    print(f"Video: {video_path} · {len(cycles)} análisis · "
          f"{sum(len(b) for _, b in detections)} rostros · detección {detect_s:.2f} s")
    print(f"\n{'Modo':<18} {'SFace':>6} {'Evitadas':>9} {'SFace (s)':>10} {'ms/análisis':>12} {'Confirmados':>12}")
    for name, recheck_s in (("Sin seguimiento", 0.0), ("Con seguimiento", 1.0)):
        t0 = time.time()
        r = simulate(detections, recheck_s, THRESHOLD, CONFIRM_FRAMES, embed_fn)
        elapsed = time.time() - t0
        per_cycle = (elapsed + detect_s) / len(cycles) * 1000
        print(f"{name:<18} {r['embeds']:>6} {r['skipped']:>9} {elapsed:>10.2f} {per_cycle:>12.1f} {r['confirmed_frames']:>12}")
    return 0


def main(paths: list[str]) -> int:
    if paths[:1] == ["--video"]:
        if len(paths) != 3:
            print(__doc__); return 1
        return run_video(paths[1], paths[2])
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
