"""Captura de video en un hilo independiente.

La captura está separada del procesamiento: este hilo solo lee fotogramas de
la cámara USB y conserva el más reciente. Si la cámara se desconecta, reintenta
con espera progresiva (1 s → 10 s) sin detener la aplicación.
"""
from __future__ import annotations

import glob
import logging
import math
import os
import threading
import time
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("faceguard.camera")


def list_cameras() -> list[dict[str, Any]]:
    devices = []
    for path in sorted(glob.glob("/dev/video*")):
        try:
            idx = int(path.replace("/dev/video", ""))
        except ValueError:
            continue
        name = path
        try:
            with open(f"/sys/class/video4linux/video{idx}/name") as fh:
                name = fh.read().strip()
        except OSError:
            pass
        devices.append({"index": idx, "path": path, "name": name})
    return devices


class SyntheticSource:
    """Fuente de video simulada para el modo demostración (sin cámara real)."""

    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.t0 = time.time()
        self.boxes: list[tuple[int, int, int, int]] = []

    def read(self) -> tuple[bool, np.ndarray]:
        t = time.time() - self.t0
        frame = np.zeros((self.h, self.w, 3), np.uint8)
        frame[:] = (28, 22, 18)
        # cuadrícula de fondo
        for x in range(0, self.w, 40):
            cv2.line(frame, (x, 0), (x, self.h), (40, 34, 30), 1)
        for y in range(0, self.h, 40):
            cv2.line(frame, (0, y), (self.w, y), (40, 34, 30), 1)
        # línea de barrido
        sy = int((t * 80) % self.h)
        cv2.line(frame, (0, sy), (self.w, sy), (120, 80, 20), 1)
        # siluetas genéricas (no son personas reales)
        boxes = []
        n = 1 + int(t / 12) % 2  # alterna entre 1 y 2 siluetas
        for i, phase in enumerate((0.0, 2.1)[:n]):
            cx = int(self.w * (0.3 + 0.4 * i) + 50 * math.sin(t * 0.6 + phase))
            cy = int(self.h * 0.45 + 10 * math.cos(t * 0.8 + phase))
            cv2.ellipse(frame, (cx, cy), (38, 48), 0, 0, 360, (70, 70, 70), -1)
            cv2.ellipse(frame, (cx, cy + 120), (75, 60), 0, 180, 360, (60, 60, 60), -1)
            boxes.append((cx - 38, cy - 48, 76, 96))
        self.boxes = boxes
        cv2.rectangle(frame, (0, self.h - 28), (self.w, self.h), (0, 0, 0), -1)
        cv2.putText(frame, "MODO DEMOSTRACION - VIDEO SIMULADO", (10, self.h - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1, cv2.LINE_AA)
        time.sleep(1 / 15)
        return True, frame

    def release(self) -> None:
        pass


class CameraService:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_ts = 0.0
        self._frame_id = 0
        self.index = 0
        self.width = 640
        self.height = 480
        self.synthetic = False
        self.connected = False
        self.running = False
        self.error: str | None = None
        self.capture_fps = 0.0
        self.reconnects = 0
        self.on_status_change = None  # callback(connected: bool, message: str)
        self.demo_boxes: list[tuple[int, int, int, int]] = []

    # ----------------------------------------------------------- control
    def start(self, index: int, width: int, height: int, synthetic: bool = False) -> None:
        self.stop()
        self.index, self.width, self.height, self.synthetic = index, width, height, synthetic
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="camera-capture")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self.running = False
        self._set_connected(False, "Monitoreo detenido")
        with self._lock:
            self._frame = None

    def latest(self) -> tuple[np.ndarray | None, int, float]:
        with self._lock:
            return self._frame, self._frame_id, self._frame_ts

    # ------------------------------------------------------------- hilo
    def _open(self):
        if self.synthetic:
            return SyntheticSource(self.width, self.height)
        source = os.getenv("FACEGUARD_CAMERA_SOURCE")  # opcional: archivo de video o URL RTSP para pruebas
        if source:
            cap = cv2.VideoCapture(source)
            return cap if cap.isOpened() else None
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2) if hasattr(cv2, "CAP_V4L2") else cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # menos carga USB
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # siempre el fotograma más reciente
        return cap

    def _set_connected(self, value: bool, message: str) -> None:
        changed = value != self.connected
        self.connected = value
        self.error = None if value else message
        if changed and self.on_status_change:
            try:
                self.on_status_change(value, message)
            except Exception:
                log.exception("on_status_change")

    def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            cap = self._open()
            if cap is None:
                self._set_connected(False, f"No se pudo abrir la cámara /dev/video{self.index}")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 10)
                self.reconnects += 1
                continue
            backoff = 1.0
            self._set_connected(True, "Cámara conectada")
            failures, count, t_last = 0, 0, time.time()
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok and os.getenv("FACEGUARD_CAMERA_SOURCE") and not self.synthetic:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # repetir el video de prueba
                    ok, frame = cap.read()
                    time.sleep(1 / 15)
                elif ok and os.getenv("FACEGUARD_CAMERA_SOURCE") and not self.synthetic:
                    time.sleep(1 / 15)  # simula la tasa de una cámara real
                if not ok or frame is None:
                    failures += 1
                    if failures >= 10:  # ~ desconexión física
                        break
                    time.sleep(0.05)
                    continue
                failures = 0
                if self.synthetic:
                    self.demo_boxes = list(cap.boxes)
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
                    self._frame_ts = time.time()
                count += 1
                if time.time() - t_last >= 2:
                    self.capture_fps = round(count / (time.time() - t_last), 1)
                    count, t_last = 0, time.time()
            cap.release()
            if not self._stop.is_set():
                log.warning("Cámara desconectada; reintentando…")
                self._set_connected(False, "Cámara desconectada; reintentando conexión")
                with self._lock:
                    self._frame = None
                self.reconnects += 1
                self._stop.wait(1)

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "connected": self.connected,
            "synthetic": self.synthetic,
            "index": self.index,
            "resolution": f"{self.width}x{self.height}",
            "capture_fps": self.capture_fps if self.connected else 0,
            "error": self.error,
            "reconnects": self.reconnects,
        }


camera = CameraService()
