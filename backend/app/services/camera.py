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

from app.core import compat

log = logging.getLogger("faceguard.camera")

# En Windows no existe /dev/video*: las cámaras se detectan probando índices
# con OpenCV. Como abrir una cámara tarda, el resultado se guarda unos segundos.
_PROBE_MAX_INDEX = int(os.getenv("FACEGUARD_CAMERA_PROBE_MAX", "5"))
_PROBE_TTL_S = 60.0
_probe_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
_probe_lock = threading.Lock()


def list_cameras() -> list[dict[str, Any]]:
    """Cámaras de video disponibles: [{index, path, name}]."""
    if compat.use_picamera2():
        return _list_csi()
    if compat.IS_LINUX:
        return _list_v4l2()
    return _list_by_probing()


def _quiet_opencv() -> int | None:
    """Silencia temporalmente los avisos de OpenCV al probar índices inexistentes."""
    try:
        prev = cv2.utils.logging.getLogLevel()
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        return prev
    except Exception:
        return None


def _restore_opencv(prev: int | None) -> None:
    if prev is not None:
        try:
            cv2.utils.logging.setLogLevel(prev)
        except Exception:
            pass


def _list_by_probing() -> list[dict[str, Any]]:
    global _probe_cache
    with _probe_lock:
        ts, cached = _probe_cache
        if time.time() - ts < _PROBE_TTL_S:
            return [dict(d) for d in cached]
        backend_name, api = compat.camera_backends(cv2)[0]
        devices = []
        prev = _quiet_opencv()
        try:
            for idx in range(_PROBE_MAX_INDEX + 1):
                # La cámara que FaceGuard ya está usando no se vuelve a abrir
                # (en Windows una webcam solo admite un proceso/conexión a la vez).
                if camera.running and camera.connected and not camera.synthetic and idx == camera.index:
                    devices.append({"index": idx, "path": compat.camera_label(idx),
                                    "name": f"Cámara USB / webcam (en uso, {camera.backend or backend_name})"})
                    continue
                cap = cv2.VideoCapture(idx, api)
                try:
                    if cap.isOpened():
                        devices.append({"index": idx, "path": compat.camera_label(idx),
                                        "name": f"Cámara USB / webcam ({backend_name})"})
                finally:
                    cap.release()
        finally:
            _restore_opencv(prev)
        _probe_cache = (time.time(), devices)
        return [dict(d) for d in devices]


def _list_v4l2() -> list[dict[str, Any]]:
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


def _list_csi() -> list[dict[str, Any]]:
    try:
        from picamera2 import Picamera2  # apt: python3-picamera2
        infos = Picamera2.global_camera_info()
    except Exception as exc:
        log.warning("picamera2 no disponible: %s", exc)
        return []
    return [{"index": i, "path": f"CSI {i}", "name": info.get("Model", "Cámara CSI")} for i, info in enumerate(infos)]


class Picamera2Source:
    """Cámara CSI de Raspberry Pi (libcamera) con la misma interfaz que cv2.VideoCapture."""

    def __init__(self, index: int, width: int, height: int) -> None:
        from picamera2 import Picamera2
        self.cam = Picamera2(index)
        cfg = self.cam.create_video_configuration(main={"size": (width, height), "format": "RGB888"}, buffer_count=2)
        self.cam.configure(cfg)
        self.cam.start()

    def isOpened(self) -> bool:  # noqa: N802 (misma API que OpenCV)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        try:
            return True, self.cam.capture_array("main")  # RGB888 de picamera2 = orden BGR de OpenCV
        except Exception:
            return False, None

    def set(self, *_args) -> bool:
        return False

    def release(self) -> None:
        try:
            self.cam.stop()
            self.cam.close()
        except Exception:
            pass


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
        self.backend: str | None = None  # backend de OpenCV con el que se abrió (v4l2, dshow, msmf…)

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
            self.backend = "archivo/url"
            return cap if cap.isOpened() else None
        if compat.use_picamera2():
            try:
                self.backend = "picamera2"
                return Picamera2Source(self.index, self.width, self.height)
            except Exception as exc:
                log.warning("No se pudo abrir la cámara CSI %s: %s", self.index, exc)
                return None
        # V4L2 en Raspberry Pi OS; DirectShow → Media Foundation en Windows.
        cap = None
        for name, api in compat.camera_backends(cv2):
            cap = cv2.VideoCapture(self.index, api)
            if cap.isOpened():
                self.backend = name
                break
            cap.release()
            cap = None
        if cap is None:
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
                self._set_connected(False, f"No se pudo abrir la cámara {compat.camera_label(self.index)}")
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
            "device": compat.camera_label(self.index),
            "backend": self.backend if self.connected else None,
            "resolution": f"{self.width}x{self.height}",
            "capture_fps": self.capture_fps if self.connected else 0,
            "error": self.error,
            "reconnects": self.reconnects,
        }


camera = CameraService()
