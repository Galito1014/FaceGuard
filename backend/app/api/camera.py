from __future__ import annotations

import asyncio
import time

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.config import config
from app.core.audit import audit
from app.core.crypto import save_encrypted_file
from app.core.security import client_ip, require
from app.services import runtime
from app.services.camera import camera, list_cameras
from app.services.events import create_event, serialize_event
from app.services.pipeline import pipeline
from app.services.settings_store import settings

router = APIRouter(prefix="/api/camera", tags=["camera"])

RESOLUTIONS = [(320, 240), (640, 480), (800, 600), (1280, 720)]


@router.get("/status")
def status(user: dict = Depends(require("camera.view"))):
    return {"camera": camera.status(), "engine": pipeline.status(),
            "devices": list_cameras(), "resolutions": [f"{w}x{h}" for w, h in RESOLUTIONS]}


@router.post("/start")
def start(request: Request, user: dict = Depends(require("camera.control"))):
    settings.update({"monitoring_enabled": True})
    if not camera.running:
        runtime.start_monitoring()
    audit(user, "iniciar monitoreo", ip=client_ip(request))
    return camera.status()


@router.post("/stop")
def stop(request: Request, user: dict = Depends(require("camera.control"))):
    settings.update({"monitoring_enabled": False})
    if camera.running:
        runtime.stop_monitoring()
    audit(user, "detener monitoreo", ip=client_ip(request))
    return camera.status()


class ResolutionIn(BaseModel):
    resolution: str = Field(pattern=r"^\d{3,4}x\d{3,4}$")


@router.post("/resolution")
def set_resolution(body: ResolutionIn, request: Request, user: dict = Depends(require("camera.control"))):
    w, h = (int(v) for v in body.resolution.split("x"))
    if (w, h) not in RESOLUTIONS:
        raise HTTPException(400, "Resolución no soportada.")
    settings.update({"camera_width": w, "camera_height": h})
    audit(user, "cambiar resolución", target=body.resolution, ip=client_ip(request))
    return camera.status()


@router.get("/stream")
async def stream(request: Request, user: dict = Depends(require("camera.view"))):
    """Video en vivo MJPEG con los recuadros de detección (≈12 fps)."""

    async def gen():
        last = -1
        while True:
            if await request.is_disconnected():
                break
            frame, fid, _ = camera.latest()
            if frame is None or fid == last:
                await asyncio.sleep(0.08 if frame is not None else 0.5)
                continue
            last = fid
            img = await asyncio.to_thread(pipeline.overlay, frame)
            ok, jpg = await asyncio.to_thread(cv2.imencode, ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
            await asyncio.sleep(1 / 12)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


class CaptureIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.post("/capture")
def capture(body: CaptureIn, request: Request, user: dict = Depends(require("camera.capture"))):
    """Captura autorizada: requiere motivo, queda cifrada y auditada."""
    frame, _, _ = camera.latest()
    if frame is None:
        raise HTTPException(409, "No hay imagen disponible: la cámara no está activa.")
    img = pipeline.overlay(frame)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    snap = save_encrypted_file("snapshots", jpg.tobytes())
    row = create_event("captura", config.camera_name, faces_count=pipeline.faces_now, snapshot_file=snap,
                       is_simulated=camera.synthetic,
                       message=f"Captura autorizada por {user['username']}: {body.reason}")
    audit(user, "captura autorizada", target=row["uid"], details=body.reason, ip=client_ip(request))
    return serialize_event(row)
