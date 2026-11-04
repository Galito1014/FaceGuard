"""Seguimiento de rostros: asociación entre ciclos y racha por rostro."""
from app.services.tracker import TRACK_TTL_SECONDS, FaceTracker
from scripts.benchmark_engine import simulate

META_A = {"entry_id": 1}
META_B = {"entry_id": 2}


def test_caja_que_se_mueve_conserva_track():
    t = FaceTracker()
    a = t.update([(100, 100, 80, 80)], 0.0)[0]
    b = t.update([(105, 102, 80, 80)], 0.25)[0]
    assert a.id == b.id


def test_caja_lejana_crea_otro_track():
    t = FaceTracker()
    a = t.update([(0, 0, 80, 80)], 0.0)[0]
    b = t.update([(300, 300, 80, 80)], 0.25)[0]
    assert a.id != b.id


def test_track_no_se_asocia_dos_veces_en_un_ciclo():
    t = FaceTracker()
    t.update([(100, 100, 80, 80)], 0.0)
    a, b = t.update([(100, 100, 80, 80), (102, 100, 80, 80)], 0.25)
    assert a.id != b.id


def test_rostro_perdido_un_ciclo_conserva_racha():
    t = FaceTracker()
    tr = t.update([(100, 100, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 3, 0.0)
    t.update([], 0.25)
    assert t.update([(100, 100, 80, 80)], 0.5)[0].streak == 1


def test_track_expira_tras_el_ttl():
    t = FaceTracker()
    a = t.update([(100, 100, 80, 80)], 0.0)[0]
    b = t.update([(100, 100, 80, 80)], TRACK_TTL_SECONDS + 0.01)[0]
    assert a.id != b.id


def test_needs_embedding_por_estado():
    t = FaceTracker()
    tr = t.update([(100, 100, 80, 80)], 0.0)[0]
    assert t.needs_embedding(tr, 0.0, 1.0)                 # nuevo
    t.record_result(tr, None, 0.1, 0.42, 2, 0.0)
    assert not t.needs_embedding(tr, 0.5, 1.0)             # descartado, antes del intervalo
    assert t.needs_embedding(tr, 1.0, 1.0)                 # descartado, tras el intervalo
    assert t.needs_embedding(tr, 0.1, 0.0)                 # intervalo 0: siempre
    t.record_result(tr, META_A, 0.6, 0.42, 2, 1.0)
    assert t.needs_embedding(tr, 1.1, 1.0)                 # en verificación
    t.record_result(tr, META_A, 0.6, 0.42, 2, 1.1)
    assert tr.confirmed and not t.needs_embedding(tr, 1.2, 1.0)


def test_dos_rostros_iguales_a_una_persona_no_confirman_en_un_fotograma():
    t = FaceTracker()
    a, b = t.update([(0, 0, 80, 80), (300, 0, 80, 80)], 0.0)
    t.record_result(a, META_A, 0.6, 0.42, 2, 0.0)
    t.record_result(b, META_A, 0.6, 0.42, 2, 0.0)
    assert not a.confirmed and not b.confirmed


def test_racha_se_reinicia_bajo_el_umbral_y_con_otra_persona():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 2, 0.0)
    t.record_result(tr, META_B, 0.6, 0.42, 2, 0.1)
    assert tr.streak == 1 and not tr.confirmed
    t.record_result(tr, META_B, 0.6, 0.42, 2, 0.2)
    assert tr.confirmed
    t.record_result(tr, META_B, 0.3, 0.42, 2, 0.3)
    assert tr.streak == 0 and not tr.confirmed


def test_confirm_frames_1_confirma_de_inmediato():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, META_A, 0.6, 0.42, 1, 0.0)
    assert tr.confirmed


def test_galeria_vacia_no_genera_candidato():
    t = FaceTracker()
    tr = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.record_result(tr, None, 0.0, 0.42, 1, 0.0)
    assert tr.streak == 0 and not tr.confirmed and tr.meta is None


def test_reset_borra_los_tracks():
    t = FaceTracker()
    a = t.update([(0, 0, 80, 80)], 0.0)[0]
    t.reset()
    assert t.update([(0, 0, 80, 80)], 0.1)[0].id != a.id


def test_simulate_compara_con_y_sin_seguimiento():
    det = [(i * 0.25, [(100, 100, 80, 80)]) for i in range(8)]
    fn = lambda c, f: (None, 0.1)  # noqa: E731
    assert simulate(det, 0.0, 0.42, 2, fn)["embeds"] == 8
    con = simulate(det, 1.0, 0.42, 2, fn)
    assert (con["embeds"], con["skipped"]) == (2, 6)


def test_simulate_cuenta_fotogramas_confirmados():
    det = [(i * 0.25, [(100, 100, 80, 80)]) for i in range(4)]
    assert simulate(det, 1.0, 0.42, 2, lambda c, f: (META_A, 0.6))["confirmed_frames"] == 3
