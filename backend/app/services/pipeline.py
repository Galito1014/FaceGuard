"""Procesamiento de video: detección, comparación y generación de alertas.

Corre en su propio hilo, separado de la captura. En cada ciclo toma el
fotograma más reciente, lo reduce, detecta rostros, calcula la plantilla de
cada uno cuando hace falta y la compara con la galería (lista de alerta).
El seguimiento de rostros (tracker.py) evita repetir SFace, el paso más
costoso, con una persona que ya se analizó hace poco.

Medidas contra falsos positivos y alertas repetidas:
  1. Umbral de similitud configurable (match_threshold).
  2. Confirmación temporal: el mismo rostro debe coincidir con la misma persona
     en N análisis consecutivos (confirm_frames) antes de generar la alerta.
  3. Tamaño mínimo de rostro y confianza mínima del detector.
  4. Deduplicación: una persona no genera otra alerta durante dedup_seconds.
  5. Toda coincidencia queda "Pendiente de revisión" hasta que un operador
     la confirme o la marque como falso positivo. El sistema no toma ninguna
     acción contra la persona.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import cv2
import numpy as np

from app.config import config
from app.core.crypto import save_encrypted_file
from app.core.database import query
from app.services.camera import camera
from app.services.events import create_event
from app.services.face_engine import Face, engine, gallery
from app.services.gpio import gpio
from app.services.realtime import hub
from app.services.settings_store import settings
from app.services.tracker import FaceTracker

log = logging.getLogger("faceguard.pipeline")

GREEN = (90, 200, 60)
RED = (40, 40, 235)
AMBER = (0, 170, 255)


class Pipeline:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._overlay: list[dict[str, Any]] = []
        self._overlay_ts = 0.0
        self._tracker = FaceTracker()
        self._gallery_version = gallery.version
        self._last_alert: dict[int, float] = {}
        self._last_detection_log = 0.0
        self._next_demo_match = time.time() + 20
        self.running = False
        self.processing_fps = 0.0
        self.latency_ms = 0.0
        self.faces_now = 0
        self.frames_processed = 0
        self.alerts_generated = 0
        self.embeds_computed = 0
        self.embeds_skipped = 0
        self.error: str | None = None

    # ------------------------------------------------------------- control
    def start(self) -> None:
        self.stop()
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="face-pipeline")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self.running = False
        self.faces_now = 0
        with self._lock:
            self._overlay = []

    def reset_tracking(self) -> None:
        self._tracker.reset()
        self._last_alert.clear()

    # ------------------------------------------------------------ superposición
    def overlay(self, frame: np.ndarray) -> np.ndarray:
        """Dibuja los últimos resultados sobre un fotograma (para el video en vivo)."""
        out = frame.copy()
        with self._lock:
            items = list(self._overlay) if time.time() - self._overlay_ts < 1.5 else []
        for it in items:
            x, y, w, h = it["box"]
            color = RED if it["match"] else (AMBER if it.get("candidate") else GREEN)
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
            # esquinas reforzadas
            L = max(8, w // 6)
            for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
                cv2.line(out, (cx, cy), (cx + dx * L, cy), color, 4)
                cv2.line(out, (cx, cy), (cx, cy + dy * L), color, 4)
            label = it["label"]
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            ty = max(th + 6, y - 6)
            cv2.rectangle(out, (x, ty - th - 6), (x + tw + 8, ty + 2), color, -1)
            cv2.putText(out, label, (x + 4, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        hud = f"{config.camera_name}  |  rostros: {len(items)}  |  {self.processing_fps:.1f} FPS"
        (tw, th), _ = cv2.getTextSize(hud, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        x0 = out.shape[1] - tw - 16
        band = out[6:th + 18, x0 - 2:out.shape[1] - 6]
        band[:] = (band * 0.35).astype(band.dtype)  # fondo oscuro semitransparente
        cv2.putText(out, hud, (x0 + 4, th + 11), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 80), 1, cv2.LINE_AA)
        return out

    # ------------------------------------------------------------------ hilo
    def _loop(self) -> None:
        last_id = -1
        count, t_last = 0, time.time()
        while not self._stop.is_set():
            cfg = settings.all()
            interval = cfg["process_interval_ms"] / 1000
            t0 = time.time()
            frame, fid, _ = camera.latest()
            if frame is None or fid == last_id:
                self.faces_now = 0 if frame is None else self.faces_now
                self._stop.wait(0.05)
                continue
            last_id = fid
            try:
                if cfg["demo_mode"]:
                    self._process_demo(frame, cfg)
                else:
                    self._process_real(frame, cfg)
                self.error = None
            except Exception as exc:  # nunca detener el hilo por un error puntual
                self.error = f"{exc.__class__.__name__}: {exc}"
                log.exception("Error en el procesamiento")
                self._stop.wait(1)
            self.frames_processed += 1
            count += 1
            self.latency_ms = round((time.time() - t0) * 1000, 1)
            if time.time() - t_last >= 2:
                self.processing_fps = round(count / (time.time() - t_last), 1)
                count, t_last = 0, time.time()
            # Respeta la frecuencia configurada para no saturar la CPU.
            self._stop.wait(max(0.0, interval - (time.time() - t0)))

    # ---------------------------------------------------------- modo real
    def _process_real(self, frame: np.ndarray, cfg: dict[str, Any], now: float | None = None) -> None:
        if not engine.ready:
            self.error = engine.error
            self._stop.wait(1)
            return
        now = time.time() if now is None else now
        if gallery.version != self._gallery_version:
            # La lista cambió: se vuelve a analizar a quienes ya estaban en cuadro.
            self._gallery_version = gallery.version
            self._tracker.reset()
        faces, small, _ = engine.detect(frame, cfg["process_width"], cfg["detection_confidence"], cfg["min_face_size"])
        tracks = self._tracker.update([f.box for f in faces], now)
        recheck_s = cfg["recheck_interval_ms"] / 1000
        overlay = []
        for face, track in zip(faces, tracks):
            if self._tracker.needs_embedding(track, now, recheck_s):
                face.embedding = engine.embed(small, face)
                meta, sim = gallery.best_match(face.embedding)
                self._tracker.record_result(track, meta, sim, cfg["match_threshold"], cfg["confirm_frames"], now)
                self.embeds_computed += 1
            else:
                self.embeds_skipped += 1
            sim = track.sim
            face.best_score = sim
            is_candidate = track.streak > 0
            confirmed = track.confirmed
            if confirmed:
                face.match = {**track.meta, "score": sim}
                self._maybe_alert(frame, face, cfg, simulated=False)
            label = (f"POSIBLE COINCIDENCIA {sim:.2f}" if confirmed else
                     f"verificando… {sim:.2f}" if is_candidate else
                     f"sin coincidencia {sim:.2f}" if gallery.size else f"rostro {face.score:.2f}")
            overlay.append({"box": face.box, "match": confirmed, "candidate": is_candidate and not confirmed,
                            "label": label})
        self._publish_overlay(overlay)
        unmatched = [f.best_score for f in faces if not f.match]
        best = max(unmatched, default=None) if gallery.size else None
        self._log_detection(len(faces), best, False, matched=len(faces) - len(unmatched))

    # ---------------------------------------------------- modo demostración
    def _process_demo(self, frame: np.ndarray, cfg: dict[str, Any]) -> None:
        boxes = camera.demo_boxes
        overlay = []
        trigger = time.time() >= self._next_demo_match
        for i, box in enumerate(boxes):
            sim = random.uniform(0.12, 0.30)
            match = trigger and i == 0
            overlay.append({"box": box, "match": match,
                            "label": f"[SIMULADO] {'POSIBLE COINCIDENCIA' if match else 'sin coincidencia'} "
                                     f"{0.63 if match else sim:.2f}"})
        self._publish_overlay(overlay)
        if trigger and boxes:
            self._next_demo_match = time.time() + random.uniform(45, 90)
            self.simulate_alert(frame, boxes[0])
        self._log_detection(len(boxes), None, True)

    def simulate_alert(self, frame: np.ndarray | None = None, box: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
        """Genera una alerta de prueba claramente marcada como simulada."""
        entries = query("SELECT id, uid, full_name, alert_level FROM blacklist WHERE is_simulated = 1 AND status='activo'")
        if entries:
            e = random.choice(entries)
            meta = {"entry_id": e["id"], "uid": e["uid"], "name": e["full_name"], "level": e["alert_level"]}
        else:
            meta = {"entry_id": None, "uid": "SIM-0000", "name": "Persona ficticia (demo)",
                    "level": random.choice(["bajo", "medio", "alto"])}
        if frame is None:
            frame, _, _ = camera.latest()
        if frame is None:
            frame = np.full((480, 640, 3), 30, np.uint8)
        if box is None:
            h, w = frame.shape[:2]
            box = (w // 2 - 60, h // 2 - 80, 120, 150)
        face = Face(box=box, score=0.99, raw=np.zeros(15, np.float32))
        face.match = {**meta, "score": round(random.uniform(0.55, 0.78), 3)}
        return self._maybe_alert(frame, face, settings.all(), simulated=True, force=True)

    # ------------------------------------------------------------- alertas
    def _maybe_alert(self, frame: np.ndarray, face: Face, cfg: dict[str, Any], simulated: bool,
                     force: bool = False) -> dict[str, Any] | None:
        m = face.match
        key = m["entry_id"] if m["entry_id"] is not None else -1
        now = time.time()
        if not force and now - self._last_alert.get(key, 0) < cfg["dedup_seconds"]:
            return None  # evita alertas repetidas del mismo evento
        self._last_alert[key] = now
        snap = self._snapshot(frame, face.box, simulated)
        level = m["level"]
        notify = cfg["alerts_enabled"]
        row = create_event(
            "coincidencia", config.camera_name, entry=m, score=m["score"], level=level, faces_count=1,
            review_status="pendiente", snapshot_file=snap, is_simulated=simulated,
            message=("[SIMULADO] " if simulated else "") + f"Posible coincidencia con {m['uid']} — requiere revisión humana",
            notify=notify,
        )
        self.alerts_generated += 1
        if notify:
            row["gpio"] = gpio.alarm(level, cfg)
        log.info("Alerta %s (%s, %.2f)%s", row["uid"], m["uid"], m["score"], " [simulada]" if simulated else "")
        return row

    @staticmethod
    def _snapshot(frame: np.ndarray, box: tuple[int, int, int, int], simulated: bool) -> str:
        """Recorte del rostro con margen. Solo se guarda para posibles coincidencias."""
        h, w = frame.shape[:2]
        x, y, bw, bh = box
        mx, my = int(bw * 0.6), int(bh * 0.6)
        x0, y0 = max(0, x - mx), max(0, y - my)
        x1, y1 = min(w, x + bw + mx), min(h, y + bh + my)
        crop = frame[y0:y1, x0:x1].copy()
        if crop.size == 0:
            crop = frame.copy()
        if simulated:
            cv2.putText(crop, "SIMULADO", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA)
        ok, jpg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return save_encrypted_file("snapshots", jpg.tobytes())

    def _log_detection(self, n_faces: int, best: float | None, simulated: bool, matched: int = 0) -> None:
        self.faces_now = n_faces
        if n_faces == 0:
            return
        cfg = settings.all()
        if time.time() - self._last_detection_log < cfg["detection_log_seconds"]:
            return
        self._last_detection_log = time.time()
        # Evento sin imagen: no se guardan fotos de personas sin coincidencia.
        create_event("deteccion", config.camera_name, faces_count=n_faces, score=best, is_simulated=simulated,
                     message=("[SIMULADO] " if simulated else "") + f"{n_faces} rostro(s) detectado(s)"
                     + (f"; {matched} con posible coincidencia (ver alerta)" if matched else "; sin coincidencia confirmada"))

    def _publish_overlay(self, overlay: list[dict[str, Any]]) -> None:
        with self._lock:
            self._overlay = overlay
            self._overlay_ts = time.time()

    def status(self) -> dict[str, Any]:
        cfg = settings.all()
        if cfg["demo_mode"]:
            state, label = "demo", "Simulación (modo demostración)"
        elif not engine.ready:
            state, label = "error", engine.error or "Motor no cargado"
        elif not self.running:
            state, label = "detenido", "Detenido"
        elif not camera.connected:
            state, label = "esperando", "Esperando cámara"
        elif self.error:
            state, label = "error", self.error
        else:
            state, label = "activo", "Activo"
        return {
            "state": state,
            "label": label,
            "running": self.running,
            "engine_ready": engine.ready,
            "models": "YuNet 2023mar + SFace 2021dec (OpenCV DNN)",
            "gallery_size": gallery.size,
            "processing_fps": self.processing_fps if self.running else 0,
            "latency_ms": self.latency_ms,
            "faces_now": self.faces_now,
            "frames_processed": self.frames_processed,
            "alerts_generated": self.alerts_generated,
            "embeds_computed": self.embeds_computed,
            "embeds_skipped": self.embeds_skipped,
            "ws_clients": hub.count,
        }


pipeline = Pipeline()
