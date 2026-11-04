"""Procesamiento con seguimiento: SFace solo se ejecuta cuando hace falta."""
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.face_engine import Face, engine, gallery
from app.services.pipeline import pipeline
from app.services.settings_store import settings
from app.services.tracker import FULL_CHECK_SECONDS

META = {"entry_id": 1, "uid": "BL-1", "name": "Persona de prueba", "level": "medio", "is_simulated": False}


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(
        boxes=[(100, 100, 80, 80)], best_match=(None, 0.1), embed_calls=0, alerts=[],
        frame=np.zeros((480, 640, 3), np.uint8),
        cfg={**settings.all(), "confirm_frames": 2, "recheck_interval_ms": 1000},
    )

    def fake_detect(frame, width, conf, min_size):
        return [Face(box=b, score=0.9, raw=np.zeros(15, np.float32)) for b in state.boxes], frame, 1.0

    def fake_embed(small, face):
        state.embed_calls += 1
        return np.ones(128, np.float32)

    monkeypatch.setattr(engine, "ready", True)
    monkeypatch.setattr(engine, "detect", fake_detect)
    monkeypatch.setattr(engine, "embed", fake_embed)
    monkeypatch.setattr(gallery, "best_match", lambda vec, threshold=None: state.best_match)
    monkeypatch.setattr(pipeline, "_maybe_alert", lambda frame, face, cfg, simulated: state.alerts.append(face.match))
    monkeypatch.setattr(pipeline, "_log_detection", lambda *a, **k: None)
    pipeline.reset_tracking()
    pipeline.embeds_computed = 0
    pipeline.embeds_skipped = 0
    return state


def run_cycles(env, cfg, n):
    for i in range(n):
        pipeline._process_real(env.frame, cfg, now=i * 0.25)


def test_rostro_quieto_se_reconoce_una_vez_por_segundo_tras_el_inicio(env):
    run_cycles(env, env.cfg, 8)  # periodo inicial: 2 s a 4 ciclos por segundo
    assert env.embed_calls == 8
    env.embed_calls = 0
    for i in range(8, 16):
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert env.embed_calls == 2


def test_ciclos_lentos_generan_alerta(env):
    env.best_match = (META, 0.6)
    for i in range(3):
        pipeline._process_real(env.frame, env.cfg, now=i * 2.0)
    assert len(env.alerts) == 2


def test_rostro_que_cruza_rapido_genera_alerta(env):
    env.best_match = (META, 0.6)
    for i in range(3):
        env.boxes = [(i * 219, 100, 100, 100)]
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert len(env.alerts) == 2


def test_primer_fotograma_malo_no_retrasa_la_alerta(env):
    for i, sim in enumerate((0.3, 0.6, 0.6)):
        env.best_match = (META, sim)
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
    assert len(env.alerts) == 1


def test_intervalo_0_reconoce_en_cada_ciclo(env):
    run_cycles(env, {**env.cfg, "recheck_interval_ms": 0}, 8)
    assert env.embed_calls == 8


def test_un_fotograma_no_dispara_alerta_con_dos_rostros(env):
    env.boxes = [(0, 0, 80, 80), (300, 0, 80, 80)]
    env.best_match = (META, 0.6)
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    assert env.alerts == []


def test_coincidencia_se_confirma_en_dos_ciclos_y_sigue_alertando(env):
    env.best_match = (META, 0.6)
    run_cycles(env, env.cfg, 3)
    assert len(env.alerts) == 2  # dedup_seconds decide dentro de _maybe_alert


def test_nueva_version_de_galeria_fuerza_reconocimiento(env):
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    gallery.version += 1
    pipeline._process_real(env.frame, env.cfg, now=0.25)
    assert env.embed_calls == 2


def test_persona_quitada_de_la_lista_deja_de_alertar(env):
    env.best_match = (META, 0.6)
    run_cycles(env, env.cfg, 2)
    env.alerts.clear()
    gallery.version += 1
    env.best_match = (None, 0.0)
    pipeline._process_real(env.frame, env.cfg, now=0.5)
    assert env.alerts == []


def test_reconocimiento_periodico_corrige_identidad_tras_un_cruce(env):
    pipeline._process_real(env.frame, env.cfg, now=0.0)
    env.best_match = (META, 0.6)  # la caja ahora es otra persona
    pipeline._process_real(env.frame, env.cfg, now=1.0)
    pipeline._process_real(env.frame, env.cfg, now=1.25)
    assert len(env.alerts) == 1


def test_cuenta_reconocimientos_hechos_y_evitados(env):
    run_cycles(env, env.cfg, 12)  # 3 s: 8 iniciales, 1 revisión y 3 evitados
    assert (pipeline.embeds_computed, pipeline.embeds_skipped) == (9, 3)


def test_galeria_vacia_no_alerta(env):
    env.best_match = (None, 0.0)
    run_cycles(env, env.cfg, 4)
    assert env.alerts == []


def test_status_incluye_contadores(env):
    run_cycles(env, env.cfg, 12)
    status = pipeline.status()
    assert status["embeds_computed"] == 9 and status["embeds_skipped"] == 3


def test_persona_autorizada_no_alerta_ni_se_registra(env, monkeypatch):
    env.best_match = ({**META, "classification": "autorizada"}, 0.7)
    logged = []
    monkeypatch.setattr(pipeline, "_log_detection", lambda n, best, sim, matched=0: logged.append(matched))
    run_cycles(env, env.cfg, 4)
    assert env.alerts == [] and logged[-1] == 0
    assert pipeline._overlay[0]["label"].startswith("autorizada") and not pipeline._overlay[0]["match"]


def test_blacklist_sigue_alertando_con_clasificacion(env):
    env.best_match = ({**META, "classification": "no_autorizada"}, 0.7)
    run_cycles(env, env.cfg, 3)
    assert len(env.alerts) == 2


def test_autorizada_no_deja_su_similitud_en_el_historial(env, monkeypatch):
    from app.core.database import query_one
    monkeypatch.undo()
    monkeypatch.setattr(gallery, "_meta", [META])
    monkeypatch.setattr(engine, "ready", True)
    monkeypatch.setattr(engine, "detect", lambda *a: ([Face(box=(1, 1, 80, 80), score=0.9, raw=np.zeros(15, np.float32))], env.frame, 1.0))
    monkeypatch.setattr(engine, "embed", lambda s, f: np.ones(128, np.float32))
    monkeypatch.setattr(gallery, "best_match", lambda vec, threshold=None: ({**META, "classification": "autorizada"}, 0.96))
    pipeline._last_detection_log = 0
    pipeline.reset_tracking()
    for i in range(3):  # en verificación y ya confirmada
        pipeline._last_detection_log = 0
        pipeline._process_real(env.frame, env.cfg, now=i * 0.25)
        row = query_one("SELECT score FROM events WHERE type = 'deteccion' ORDER BY id DESC LIMIT 1")
        assert row["score"] is None
