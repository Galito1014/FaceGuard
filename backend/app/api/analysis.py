"""Análisis de fotografías: busca coincidencias sin registrar a nadie.

La fotografía se procesa en memoria y no se guarda. Solo se conserva un recorte
del rostro cuando hay una posible coincidencia con la blacklist, igual que en
las alertas de la cámara, y queda pendiente de revisión humana.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.persons import read_photo
from app.core.audit import audit
from app.core.security import client_ip, has_perm, require
from app.services.events import create_event
from app.services.face_engine import engine, gallery
from app.services.pipeline import Pipeline
from app.services.settings_store import settings

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

SOURCE = "Análisis de fotografía"
AMBIGUOUS_MARGIN = 0.05  # similitud entre dos personas distintas que obliga a mirar ambas


def _public(match: dict[str, Any], identify: bool) -> dict[str, Any]:
    """Quien no puede consultar personas solo sabe que el rostro es de alguien autorizado."""
    hidden = match["classification"] == "autorizada" and not identify
    return {"entry_id": None if hidden else match["entry_id"], "uid": None if hidden else match["uid"],
            "name": None if hidden else match["name"], "level": None if hidden else match["level"],
            "classification": match["classification"], "score": round(match["score"], 3)}


def _face_result(img: np.ndarray, face: dict[str, Any], threshold: float, identify: bool, seen: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"box": face["box"], "detection_score": round(face["score"], 3), "quality_issues": face["issues"],
                           "match": None, "score": None, "ambiguous": False, "alternatives": []}
    if face["issues"]:
        out["result"] = "calidad_insuficiente"
        return out
    matches = gallery.top_matches(face["embedding"], threshold)
    if not matches:
        out["result"] = "desconocida"
        return out
    restricted = next((m for m in matches if m["classification"] == "no_autorizada"), None)
    chosen = restricted or matches[0]
    seen.extend(m["uid"] for m in matches)
    out["match"] = _public(chosen, identify)
    out["score"] = out["match"]["score"]
    out["alternatives"] = [_public(m, identify) for m in matches if m is not chosen]
    out["ambiguous"] = len(matches) > 1 and matches[0]["score"] - matches[1]["score"] < AMBIGUOUS_MARGIN
    if restricted is None:
        out["result"] = "autorizada"
        return out
    out["result"] = "posible_no_autorizada"
    snapshot = Pipeline._snapshot(img, tuple(face["box"]), simulated=False)
    event = create_event(
        "coincidencia", SOURCE, entry=restricted, score=restricted["score"], level=restricted["level"], faces_count=1,
        review_status="pendiente", snapshot_file=snapshot,
        message=f"Posible coincidencia con {restricted['uid']} en una fotografía analizada — requiere revisión humana",
        notify=settings.get("alerts_enabled"))
    out["alert"] = {"id": event["id"], "uid": event["uid"]}
    return out


def _analyze(data: bytes, identify: bool, seen: list[str]) -> dict[str, Any]:
    if not engine.ready:
        raise HTTPException(503, engine.error or "El motor facial no está disponible.")
    decoded = engine.detect_all(data)
    if decoded is None:
        raise HTTPException(422, "La imagen está dañada o no se puede leer.")
    img, faces = decoded
    threshold = settings.get("match_threshold")
    h, w = img.shape[:2]
    return {"image": {"width": w, "height": h}, "threshold": threshold,
            "faces": [_face_result(img, f, threshold, identify, seen) for f in faces]}


@router.post("/photo")
async def analyze_photo(request: Request, photo: UploadFile = File(...), user: dict = Depends(require("analysis.run"))):
    data = await read_photo(photo)
    seen: list[str] = []
    result = await run_in_threadpool(_analyze, data, has_perm(user, "blacklist.view"), seen)
    summary: dict[str, int] = {}
    for face in result["faces"]:
        summary[face["result"]] = summary.get(face["result"], 0) + 1
    audit(user, "análisis de fotografía", details={"rostros": len(result["faces"]), **summary, "coincidencias": seen}, ip=client_ip(request))
    return result
