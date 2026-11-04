"""Análisis de fotografías: resultado por rostro y sin registrar a nadie."""
import cv2
import numpy as np
import pytest

from app.config import config
from app.core.database import execute, query_one
from app.services.face_engine import Face, engine, gallery

HAS_MODELS = config.detector_model.exists() and config.recognizer_model.exists()
META = {"entry_id": None, "uid": "FG-1", "name": "Ana", "level": "alto", "classification": "no_autorizada", "is_simulated": False}
AUT = {**META, "uid": "FG-2", "name": "Eva", "classification": "autorizada"}


def _jpeg(img) -> bytes:
    return cv2.imencode(".jpg", img)[1].tobytes()


def _send(client, img=None):
    img = np.full((400, 600, 3), 128, np.uint8) if img is None else img
    return client.post("/api/analysis/photo", files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")})


@pytest.fixture
def faces(monkeypatch):
    """Un rostro falso por cada (caja, resultados de galería)."""
    state = {"items": []}

    def fake_detect(img, width, conf, min_size):
        out = [Face(box=b, score=0.95, raw=np.zeros(15, np.float32)) for b, _ in state["items"]]
        return out, img, 1.0

    calls = iter(())

    def fake_embed(small, face):
        return np.ones(128, np.float32)

    def fake_top(vec, threshold, limit=3):
        return next(state["iter"])

    monkeypatch.setattr(engine, "ready", True)
    monkeypatch.setattr(engine, "detect", fake_detect)
    monkeypatch.setattr(engine, "embed", fake_embed)
    monkeypatch.setattr(gallery, "top_matches", fake_top)

    def setup(*items):
        state["items"] = list(items)
        state["iter"] = iter([m for _, m in items])
    return setup


BOX = (100, 60, 120, 120)
BOX2 = (320, 60, 120, 120)


def _texture():
    return np.random.default_rng(1).integers(40, 210, (400, 600, 3), dtype=np.uint8)


def test_rechaza_archivo_invalido(client):
    r = client.post("/api/analysis/photo", files={"photo": ("a.jpg", b"hola", "image/jpeg")})
    assert r.status_code == 415


def test_imagen_corrupta_da_error_claro(client):
    r = client.post("/api/analysis/photo", files={"photo": ("a.jpg", b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")})
    assert r.status_code == 422


def test_sin_rostros(client, faces):
    faces()
    r = _send(client)
    assert r.status_code == 200 and r.json()["faces"] == [] and r.json()["image"]["width"] == 600


def test_un_resultado_por_rostro_y_alerta_solo_con_blacklist(client, faces):
    faces((BOX, [{**META, "score": 0.6}]), (BOX2, []))
    before = query_one("SELECT COUNT(*) AS n FROM events WHERE type='coincidencia'")["n"]
    r = _send(client, _texture()).json()
    assert [f["result"] for f in r["faces"]] == ["posible_no_autorizada", "desconocida"]
    assert r["faces"][0]["score"] == pytest.approx(0.6) and r["faces"][0]["match"]["name"] == "Ana"
    assert r["faces"][0]["alert"]["uid"].startswith("EV-")
    assert r["faces"][1]["match"] is None and "alert" not in r["faces"][1]
    assert query_one("SELECT COUNT(*) AS n FROM events WHERE type='coincidencia'")["n"] == before + 1
    ev = query_one("SELECT * FROM events WHERE uid = ?", (r["faces"][0]["alert"]["uid"],))
    assert ev["review_status"] == "pendiente" and ev["camera"] == "Análisis de fotografía" and ev["snapshot_file"]


def test_autorizada_no_genera_alerta(client, faces):
    faces((BOX, [{**AUT, "score": 0.7}]))
    before = query_one("SELECT COUNT(*) AS n FROM events")["n"]
    r = _send(client, _texture()).json()
    assert r["faces"][0]["result"] == "autorizada"
    assert query_one("SELECT COUNT(*) AS n FROM events")["n"] == before


def test_blacklist_tiene_prioridad_y_marca_ambiguedad(client, faces):
    faces((BOX, [{**AUT, "score": 0.7}, {**META, "score": 0.68}]))
    face = _send(client, _texture()).json()["faces"][0]
    assert face["result"] == "posible_no_autorizada" and face["match"]["name"] == "Ana"
    assert face["ambiguous"] is True and [a["name"] for a in face["alternatives"]] == ["Eva"]


def test_rostro_pequeno_es_calidad_insuficiente(client, faces):
    faces(((100, 60, 30, 30), [{**META, "score": 0.9}]))
    before = query_one("SELECT COUNT(*) AS n FROM events WHERE type='coincidencia'")["n"]
    face = _send(client, _texture()).json()["faces"][0]
    assert face["result"] == "calidad_insuficiente" and face["match"] is None
    assert query_one("SELECT COUNT(*) AS n FROM events WHERE type='coincidencia'")["n"] == before


def test_analizar_no_registra_personas_ni_guarda_la_foto(client, faces):
    faces((BOX, []))
    before = query_one("SELECT COUNT(*) AS n FROM persons")["n"]
    photos = len(list((config.media_dir / "photos").glob("*.bin")))
    snaps = len(list((config.media_dir / "snapshots").glob("*.bin")))
    _send(client, _texture())
    assert query_one("SELECT COUNT(*) AS n FROM persons")["n"] == before
    assert len(list((config.media_dir / "photos").glob("*.bin"))) == photos
    assert len(list((config.media_dir / "snapshots").glob("*.bin"))) == snaps


def test_el_analisis_queda_en_auditoria(client, faces):
    faces((BOX, []))
    _send(client, _texture())
    assert query_one("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1")["action"] == "análisis de fotografía"


def test_auditor_no_analiza_y_operador_si(client, faces):
    from tests.conftest import make_user
    faces()
    assert _send(make_user(client, "auditor_analisis", "auditor")).status_code == 403
    assert _send(make_user(client, "operador_analisis", "operator")).status_code == 200


def test_imagen_enorme_se_rechaza(client, monkeypatch):
    from app.api import persons
    monkeypatch.setattr(persons, "MAX_PIXELS", 100)
    assert _send(client).status_code == 413


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_foto_real_de_persona_registrada(client):
    skimage = pytest.importorskip("skimage.data")
    img = cv2.cvtColor(skimage.astronaut(), cv2.COLOR_RGB2BGR)
    data = {"full_name": "Real", "reason": "Prueba", "legal_basis": "Dominio público", "alert_level": "bajo", "expires_at": "2099-01-01"}
    pid = client.post("/api/persons", data=data, files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")}).json()["id"]
    r = _send(client, cv2.flip(img, 1)).json()
    assert r["faces"][0]["result"] == "posible_no_autorizada"
    assert r["faces"][0]["match"]["entry_id"] == pid and r["faces"][0]["score"] > 0.6
    execute("DELETE FROM persons WHERE id = ?", (pid,))
    gallery.load()
