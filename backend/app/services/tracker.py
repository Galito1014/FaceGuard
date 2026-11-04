"""Seguimiento de rostros entre ciclos de análisis.

Asocia las cajas de cada ciclo con las del anterior por superposición (IoU) y
decide cuándo hace falta ejecutar SFace, el paso más costoso.

Una coincidencia se confirma por cualquiera de estas dos rachas:
  * la del rostro, que sobrevive a un ciclo sin detección;
  * la de la persona, que cuenta ciclos consecutivos con coincidencia y sube
    como máximo una vez por ciclo. Cubre lo que el seguimiento no puede asociar:
    rostros que cruzan muy rápido y ciclos más lentos que TRACK_TTL_SECONDS.

El seguimiento nunca debe costar una alerta: un rostro reciente se reconoce en
cada ciclo, y solo después se pasa a la revisión periódica.

Es lógica pura: recibe las cajas y el instante como parámetros, sin cámara,
OpenCV ni base de datos. Así se prueba sin hardware y puede procesar videos
con su propio reloj.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

Box = tuple[int, int, int, int]  # x, y, ancho, alto

TRACK_TTL_SECONDS = 1.0  # tiempo sin verse tras el cual se olvida un rostro
MIN_IOU = 0.3            # superposición mínima para considerarlo el mismo rostro
FULL_CHECK_SECONDS = 2.0  # un rostro reciente se reconoce en cada ciclo


@dataclass
class Track:
    id: int
    box: Box
    last_seen: float
    first_seen: float
    last_embed_at: float | None = None
    meta: dict[str, Any] | None = None
    sim: float = 0.0
    streak: int = 0
    confirmed: bool = False


def iou(a: Box, b: Box) -> float:
    """Intersección sobre unión de dos cajas (0 = separadas, 1 = idénticas)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = min(ax + aw, bx + bw) - max(ax, bx)
    ih = min(ay + ah, by + bh) - max(ay, by)
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter)


class FaceTracker:
    def __init__(self) -> None:
        self._tracks: list[Track] = []
        self._next_id = 1
        self._cycle = 0
        self._person_hits: dict[int, tuple[int, int]] = {}  # entry_id -> (racha, último ciclo)
        self._lock = threading.Lock()

    def update(self, boxes: list[Box], now: float) -> list[Track]:
        """Devuelve un track por caja, en el mismo orden que `boxes`."""
        with self._lock:
            self._cycle += 1
            self._tracks = [t for t in self._tracks if now - t.last_seen <= TRACK_TTL_SECONDS]
            pairs = sorted(
                ((iou(box, t.box), bi, ti) for bi, box in enumerate(boxes) for ti, t in enumerate(self._tracks)),
                key=lambda p: p[0], reverse=True,
            )
            assigned: dict[int, Track] = {}
            used: set[int] = set()
            for overlap, bi, ti in pairs:
                if overlap < MIN_IOU:
                    break
                if bi in assigned or ti in used:
                    continue
                assigned[bi] = self._tracks[ti]
                used.add(ti)
            result: list[Track] = []
            for bi, box in enumerate(boxes):
                track = assigned.get(bi)
                if track is None:
                    track = Track(id=self._next_id, box=box, last_seen=now, first_seen=now)
                    self._next_id += 1
                    self._tracks.append(track)
                track.box = box
                track.last_seen = now
                result.append(track)
            return result

    @staticmethod
    def needs_embedding(track: Track, now: float, recheck_s: float) -> bool:
        """Indica si hay que ejecutar SFace para este rostro en este ciclo."""
        if track.last_embed_at is None or now - track.first_seen < FULL_CHECK_SECONDS:
            return True
        if track.streak > 0 and not track.confirmed:
            return True
        return now - track.last_embed_at >= recheck_s

    def record_result(self, track: Track, meta: dict[str, Any] | None, sim: float, threshold: float,
                      confirm_frames: int, now: float) -> None:
        """Aplica el resultado de SFace a la racha del rostro."""
        track.sim = sim
        track.last_embed_at = now
        if meta is None or sim < threshold:
            track.meta = None
            track.streak = 0
            track.confirmed = False
            return
        same_person = track.meta is not None and track.meta["entry_id"] == meta["entry_id"]
        track.streak = track.streak + 1 if same_person else 1
        track.meta = meta
        person_streak = self._count_person_hit(meta["entry_id"])
        track.confirmed = max(track.streak, person_streak) >= confirm_frames

    def _count_person_hit(self, entry_id: int) -> int:
        with self._lock:
            streak, last_cycle = self._person_hits.get(entry_id, (0, -1))
            if last_cycle == self._cycle:
                return streak  # varios rostros en un ciclo cuentan una sola vez
            streak = streak + 1 if last_cycle == self._cycle - 1 else 1
            self._person_hits[entry_id] = (streak, self._cycle)
            return streak

    def reset(self) -> None:
        with self._lock:
            self._tracks = []
            self._person_hits = {}
