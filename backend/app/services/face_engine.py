"""Motor de visión: detección (YuNet) y reconocimiento facial (SFace).

Ambos modelos provienen de OpenCV Zoo, se ejecutan localmente con el módulo
DNN de OpenCV (sin Internet ni servicios externos) y funcionan en ARM64:

* YuNet (~230 KB): detector de rostros con 5 puntos de referencia.
* SFace (~37 MB): genera una plantilla de 128 valores por rostro. Su red base
  es una MobileFaceNet entrenada con la función de pérdida SFace.

La similitud entre plantillas se mide con coseno (1 = idénticas).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.config import config

log = logging.getLogger("faceguard.engine")


@dataclass
class Face:
    box: tuple[int, int, int, int]          # x, y, w, h en coordenadas de la imagen original
    score: float                            # confianza del detector
    raw: np.ndarray                         # fila YuNet (en coordenadas de la imagen procesada)
    embedding: np.ndarray | None = None
    match: dict[str, Any] | None = None     # {"entry_id", "name", "level", "score"}
    best_score: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class FaceEngine:
    def __init__(self) -> None:
        self._detector = None
        self._recognizer = None
        self._lock = threading.Lock()
        self.ready = False
        self.error: str | None = None

    def load(self) -> bool:
        with self._lock:
            self.ready = False
            det, rec = config.detector_model, config.recognizer_model
            missing = [p.name for p in (det, rec) if not p.exists()]
            if missing:
                self.error = "Modelos no encontrados: " + ", ".join(missing) + ". Ejecute scripts/download_models.sh"
                log.error(self.error)
                return False
            try:
                self._detector = cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.85, 0.3, 50)
                self._recognizer = cv2.FaceRecognizerSF.create(str(rec), "")
                self.ready = True
                self.error = None
                log.info("Motor facial cargado (OpenCV %s)", cv2.__version__)
            except cv2.error as exc:
                self.error = f"No se pudo cargar el motor: {exc}"
                log.exception(self.error)
            return self.ready

    # ------------------------------------------------------------- detección
    def detect(self, frame: np.ndarray, process_width: int, conf: float, min_size: int) -> tuple[list[Face], np.ndarray, float]:
        """Detecta rostros en una versión reducida del fotograma.

        Devuelve (rostros, imagen_reducida, escala). Las cajas se expresan en
        coordenadas del fotograma original.
        """
        h, w = frame.shape[:2]
        scale = min(1.0, process_width / float(w))
        small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else frame
        sh, sw = small.shape[:2]
        with self._lock:
            if not self.ready:
                return [], small, scale
            self._detector.setInputSize((sw, sh))
            self._detector.setScoreThreshold(conf)
            _, rows = self._detector.detect(small)
        faces: list[Face] = []
        if rows is None:
            return faces, small, scale
        for r in rows:
            x, y, fw, fh = r[:4]
            if min(fw, fh) < min_size * scale:
                continue
            box = tuple(int(round(v / scale)) for v in (x, y, fw, fh))
            faces.append(Face(box=box, score=float(r[14]), raw=r))
        return faces, small, scale

    def embed(self, small: np.ndarray, face: Face) -> np.ndarray:
        with self._lock:
            aligned = self._recognizer.alignCrop(small, face.raw)
            feat = self._recognizer.feature(aligned)
        vec = feat.flatten().astype(np.float32)
        return vec / (np.linalg.norm(vec) + 1e-9)

    def aligned_crop(self, small: np.ndarray, face: Face) -> np.ndarray:
        with self._lock:
            return self._recognizer.alignCrop(small, face.raw)

    # -------------------------------------------------- registro de fotografías
    def analyze_photo(self, image_bytes: bytes) -> dict[str, Any]:
        """Valida la calidad de una fotografía para la lista de alerta.

        Requisitos: un único rostro, confianza alta, tamaño suficiente, nitidez
        e iluminación adecuadas. Devuelve el informe y la plantilla.
        """
        report: dict[str, Any] = {"ok": False, "checks": [], "embedding": None}

        def check(name: str, ok: bool, detail: str) -> None:
            report["checks"].append({"name": name, "ok": ok, "detail": detail})

        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            check("Formato", False, "El archivo no es una imagen válida (use JPG o PNG).")
            return report
        h, w = img.shape[:2]
        check("Resolución", min(h, w) >= 200, f"{w}×{h} px (mínimo 200 px por lado)")
        if not self.ready:
            check("Motor facial", False, self.error or "Motor no disponible")
            return report

        # Para el análisis se usa como máximo 800 px de ancho.
        faces, small, scale = self.detect(img, 800, 0.6, 20)
        check("Rostros detectados", len(faces) == 1,
              "1 rostro" if len(faces) == 1 else f"{len(faces)} rostros (debe haber exactamente uno)")
        if len(faces) != 1:
            return report
        face = faces[0]
        check("Confianza de detección", face.score >= 0.85, f"{face.score:.2f} (mínimo 0.85)")
        fw = face.box[2]
        check("Tamaño del rostro", fw >= 90, f"{fw} px de ancho (mínimo 90 px)")

        x, y, bw, bh = face.box
        crop = img[max(0, y):y + bh, max(0, x):x + bw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.size else np.zeros((1, 1), np.uint8)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        check("Nitidez", sharp >= 40, f"{sharp:.0f} (mínimo 40)")
        check("Iluminación", 50 <= bright <= 210, f"brillo medio {bright:.0f} (rango 50–210)")

        report["ok"] = all(c["ok"] for c in report["checks"])
        report["embedding"] = self.embed(small, face)
        report["metrics"] = {"face_score": round(face.score, 3), "face_width": fw,
                             "sharpness": round(sharp, 1), "brightness": round(bright, 1)}
        return report


class Gallery:
    """Plantillas descifradas de la lista de alerta, en memoria (solo activas)."""

    def __init__(self) -> None:
        self._ids: list[int] = []
        self._meta: list[dict[str, Any]] = []
        self._matrix = np.zeros((0, 128), np.float32)
        self._lock = threading.Lock()

    def load(self) -> int:
        from app.core.crypto import decrypt_embedding
        from app.core.database import query, utcnow

        rows = query(
            """SELECT id, uid, full_name, alert_level, embedding_enc, is_simulated FROM blacklist
               WHERE status = 'activo' AND expires_at > ? AND embedding_enc IS NOT NULL""",
            (utcnow(),),
        )
        vecs, meta = [], []
        for r in rows:
            try:
                v = decrypt_embedding(r["embedding_enc"])
            except Exception:
                log.warning("Plantilla ilegible para %s", r["uid"])
                continue
            vecs.append(v / (np.linalg.norm(v) + 1e-9))
            meta.append({"entry_id": r["id"], "uid": r["uid"], "name": r["full_name"],
                         "level": r["alert_level"], "is_simulated": bool(r["is_simulated"])})
        with self._lock:
            self._meta = meta
            self._matrix = np.vstack(vecs).astype(np.float32) if vecs else np.zeros((0, 128), np.float32)
        log.info("Galería cargada: %d plantillas activas", len(meta))
        return len(meta)

    @property
    def size(self) -> int:
        return len(self._meta)

    def best_match(self, vec: np.ndarray) -> tuple[dict[str, Any] | None, float]:
        with self._lock:
            if not self._meta:
                return None, 0.0
            sims = self._matrix @ vec
            i = int(np.argmax(sims))
            return self._meta[i], float(sims[i])


engine = FaceEngine()
gallery = Gallery()
