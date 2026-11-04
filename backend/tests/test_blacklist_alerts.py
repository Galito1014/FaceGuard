import io

import cv2
import numpy as np
import pytest

from app.config import config
from app.services.pipeline import pipeline

HAS_MODELS = config.detector_model.exists() and config.recognizer_model.exists()


def _jpeg(img) -> bytes:
    return cv2.imencode(".jpg", img)[1].tobytes()


def _face_image():
    skimage = pytest.importorskip("skimage.data")
    return cv2.cvtColor(skimage.astronaut(), cv2.COLOR_RGB2BGR)  # NASA, dominio público


def test_rechaza_archivo_que_no_es_imagen(client):
    r = client.post("/api/persons/validate-photo", files={"photo": ("x.jpg", b"hola", "image/jpeg")})
    assert r.status_code == 415


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_rechaza_foto_sin_rostro(client):
    blank = np.full((400, 400, 3), 128, np.uint8)
    r = client.post("/api/persons/validate-photo", files={"photo": ("b.jpg", _jpeg(blank), "image/jpeg")})
    assert r.status_code == 200 and r.json()["ok"] is False


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_registro_cifrado_y_reconocimiento(client):
    img = _face_image()
    data = {"full_name": "Prueba", "reason": "Prueba automática", "legal_basis": "Imagen de dominio público",
            "alert_level": "alto", "expires_at": "2099-01-01"}
    r = client.post("/api/persons", data=data, files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")})
    assert r.status_code == 200, r.text
    entry = r.json()
    # La foto en disco está cifrada (no comienza con la firma JPEG)
    files = list((config.media_dir / "photos").glob("*.bin"))
    assert files and all(not f.read_bytes().startswith(b"\xff\xd8") for f in files)
    # La plantilla coincide con una variante de la misma imagen y no con una imagen sin rostro
    from app.services.face_engine import engine, gallery
    faces, small, _ = engine.detect(cv2.flip(img, 1), 480, 0.8, 20)
    meta, sim = gallery.best_match(engine.embed(small, faces[0]))
    assert meta["entry_id"] == entry["id"] and sim > 0.6
    # Historial de modificaciones
    client.put(f"/api/persons/{entry['id']}", data={"alert_level": "medio"})
    detail = client.get(f"/api/persons/{entry['id']}").json()
    assert [h["action"] for h in detail["history"]] == ["modificado", "creado"]
    assert client.delete(f"/api/persons/{entry['id']}").status_code == 200
    assert gallery.size == 0


def test_alerta_simulada_revision_y_deduplicacion(client):
    first = client.post("/api/demo/alert").json()
    assert first["is_simulated"] and first["review_status"] == "pendiente"
    # Revisión: confirmar exige observaciones
    assert client.post(f"/api/alerts/{first['id']}/review", json={"status": "confirmada", "notes": ""}).status_code == 422
    r = client.post(f"/api/alerts/{first['id']}/review", json={"status": "falso_positivo", "notes": "No es la persona"})
    assert r.status_code == 200 and r.json()["review_status"] == "falso_positivo"
    # Deduplicación: dos coincidencias seguidas de la misma persona generan una sola alerta
    from app.services.face_engine import Face
    frame = np.zeros((240, 320, 3), np.uint8)
    face = Face(box=(10, 10, 50, 50), score=0.9, raw=np.zeros(15, np.float32))
    face.match = {"entry_id": None, "uid": "FG-TEST", "name": "Dedup", "level": "bajo", "score": 0.7}
    cfg = {"dedup_seconds": 60, "alerts_enabled": False}
    pipeline.reset_tracking()
    assert pipeline._maybe_alert(frame, face, {**cfg}, simulated=True) is not None
    assert pipeline._maybe_alert(frame, face, {**cfg}, simulated=True) is None


def test_exportacion_csv_pdf(client):
    csv = client.get("/api/events/export?format=csv")
    assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
    pdf = client.get("/api/events/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_modo_demo_cargar_y_limpiar(client):
    r = client.post("/api/demo/seed").json()
    assert r["blacklist"] == 6 and r["events"] > 0
    sims = client.get("/api/events?simulated=1").json()["total"]
    assert sims > 0
    r = client.post("/api/demo/clear").json()
    assert r["blacklist"] == 6
    assert client.get("/api/events?simulated=1").json()["total"] == 0


def test_actividad_y_resumen(client):
    for rng in ("day", "week"):
        r = client.get(f"/api/dashboard/activity?range={rng}")
        assert r.status_code == 200 and len(r.json()["series"]) == (24 if rng == "day" else 7)
    assert client.get("/api/dashboard/summary").status_code == 200
