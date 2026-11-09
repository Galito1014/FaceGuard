"""Video en vivo compartido: se codifica una sola vez para todos los que lo miran.

Antes, cada pestaña o dispositivo con el video abierto dibujaba los recuadros y
codificaba su propio JPEG de cada fotograma. En la Raspberry Pi, con el Monitor
y el Dashboard abiertos (o varios operadores), eso se comía un núcleo entero y
el video se trababa. Ahora un solo hilo prepara cada fotograma y todas las
conexiones envían el mismo JPEG.

El hilo solo corre mientras alguien está mirando: sin espectadores no gasta CPU.
"""
from __future__ import annotations

import logging
import threading
import time

import cv2

from app.services.camera import camera
from app.services.pipeline import pipeline

log = logging.getLogger("faceguard.stream")

STREAM_FPS = 12
JPEG_QUALITY = 70


class StreamHub:
    def __init__(self, fps: int = STREAM_FPS, quality: int = JPEG_QUALITY) -> None:
        self._period = 1.0 / fps
        self._quality = quality
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._jpeg: bytes | None = None
        self._id = 0
        self._clients = 0
        self.encode_ms = 0.0
        self.fps = 0.0

    @property
    def clients(self) -> int:
        return self._clients

    # --------------------------------------------------------- espectadores
    def _ensure_thread(self) -> None:
        """Arranca el hilo si hace falta. Se llama con self._cond tomado."""
        if self._thread is None and self._clients > 0:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="live-stream")
            self._thread.start()

    def acquire(self) -> None:
        with self._cond:
            self._clients += 1
            self._ensure_thread()

    def release(self) -> None:
        with self._cond:
            self._clients = max(0, self._clients - 1)
            self._cond.notify_all()

    def wait_next(self, last_id: int, timeout: float = 1.0) -> tuple[int, bytes | None]:
        """Espera un JPEG más nuevo que `last_id`. Devuelve (id, jpeg)."""
        with self._cond:
            self._ensure_thread()  # por si el hilo terminó por un error puntual
            self._cond.wait_for(lambda: self._id != last_id, timeout)
            return self._id, self._jpeg

    # ---------------------------------------------------------------- hilo
    def _loop(self) -> None:
        last_fid = -1
        count, t_last = 0, time.time()
        try:
            while True:
                with self._cond:
                    if self._clients == 0:
                        self._thread = None
                        self._jpeg = None
                        self.fps = 0.0
                        return
                t0 = time.perf_counter()
                frame, fid, _ = camera.latest()
                if frame is None or fid == last_fid:
                    time.sleep(0.02)
                    continue
                last_fid = fid
                img = pipeline.overlay(frame)
                ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
                elapsed = time.perf_counter() - t0
                self.encode_ms = elapsed * 1000 if self.encode_ms == 0 else \
                    self.encode_ms + 0.2 * (elapsed * 1000 - self.encode_ms)
                if ok:
                    with self._cond:
                        self._jpeg = jpg.tobytes()
                        self._id += 1
                        self._cond.notify_all()
                    count += 1
                if time.time() - t_last >= 2:
                    self.fps = round(count / (time.time() - t_last), 1)
                    count, t_last = 0, time.time()
                time.sleep(max(0.0, self._period - (time.perf_counter() - t0)))
        except Exception:
            log.exception("Error en el video en vivo")
            with self._cond:
                self._thread = None

    def status(self) -> dict:
        return {"viewers": self._clients, "fps": self.fps if self._clients else 0,
                "encode_ms": round(self.encode_ms, 1)}


stream_hub = StreamHub()
