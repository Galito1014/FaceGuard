"""Alarma física (LED rojo + buzzer).

Las pruebas de hardware usan la MockFactory de gpiozero: el código es el mismo
que corre en la Raspberry Pi, solo cambia el controlador de pines.
"""
import time

import pytest

from app.core.database import query, query_one
from app.services import alarm_controller as ac
from app.services.alarm_controller import AlarmController, alarm
from app.services.settings_store import settings

gpiozero = pytest.importorskip("gpiozero")
from gpiozero import Device, DigitalOutputDevice  # noqa: E402
from gpiozero.pins.mock import MockFactory, MockPWMPin  # noqa: E402

CFG = {"gpio_enabled": True, "led_enabled": True, "buzzer_enabled": True, "buzzer_min_level": "bajo",
       "led_seconds": 1, "buzzer_seconds": 1, "buzzer_pattern": "intermitente"}


@pytest.fixture
def mock_pi(monkeypatch, client):  # client: base de datos con migraciones aplicadas
    factory = MockFactory(pin_class=MockPWMPin)
    previous = Device.pin_factory
    Device.pin_factory = factory
    monkeypatch.setattr(ac, "_has_gpio_hardware", lambda: (True, ""))
    ctrl = AlarmController()
    yield ctrl, factory
    ctrl.close()
    Device.pin_factory = previous
    factory.reset()


def _wait(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not pred():
        time.sleep(0.02)
    return pred()


def test_salidas_arrancan_apagadas(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)
    assert ctrl.mode == "hardware" and ctrl.error is None
    assert not factory.pin(17).state and not factory.pin(27).state
    assert not ctrl.alarm_active


def test_led_fijo_y_buzzer_intermitente_con_duraciones_distintas(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)
    r = ctrl.trigger("alto", {**CFG, "led_seconds": 2, "buzzer_seconds": 1}, source="prueba")
    assert r["state"] == "activada" and r["led"] and r["buzzer"]
    assert _wait(lambda: bool(factory.pin(17).state))
    # El buzzer termina antes que el LED; el LED sigue encendido.
    assert _wait(lambda: not ctrl.buzzer_on and not factory.pin(27).state, 2)
    time.sleep(0.2)
    assert bool(factory.pin(17).state)
    assert _wait(lambda: not ctrl.alarm_active, 2)
    assert not factory.pin(17).state and not factory.pin(27).state
    # Patrón intermitente: el buzzer se encendió varias veces en 1 s.
    ons = [s for s in factory.pin(27).states if s.state]
    assert len(ons) >= 3
    row = query_one("SELECT * FROM alarm_activations WHERE id = ?", (r["activation_id"],))
    assert row["state"] == "completada" and row["led_seconds"] == 2 and row["buzzer_seconds"] == 1


def test_buzzer_pasivo_usa_pwm(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27, "pasivo", 2000)
    ctrl.trigger("alto", {**CFG, "led_enabled": False, "buzzer_pattern": "continuo"}, source="prueba")
    assert _wait(lambda: ctrl.buzzer_on)
    pin = factory.pin(27)
    assert pin.frequency == 2000 and pin.state == pytest.approx(0.5)
    ctrl.silence()
    assert pin.state == 0


def test_silenciar_apaga_de_inmediato_y_queda_registrado(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)
    r = ctrl.trigger("alto", {**CFG, "led_seconds": 30, "buzzer_seconds": 30}, source="prueba")
    assert _wait(lambda: bool(factory.pin(17).state))
    assert ctrl.silence(by="operador1") is True
    assert not factory.pin(17).state and not factory.pin(27).state and not ctrl.alarm_active
    row = query_one("SELECT * FROM alarm_activations WHERE id = ?", (r["activation_id"],))
    assert row["state"] == "silenciada" and row["silenced_by"] == "operador1"
    assert ctrl.silence() is False  # no había nada que silenciar


def test_nueva_alarma_reemplaza_a_la_anterior(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)
    first = ctrl.trigger("alto", {**CFG, "led_seconds": 30}, source="prueba")
    second = ctrl.trigger("alto", CFG, source="prueba")
    assert query_one("SELECT state FROM alarm_activations WHERE id = ?", (first["activation_id"],))["state"] == "completada"
    assert _wait(lambda: not ctrl.alarm_active, 3)  # sigue la duración de la segunda (1 s), no 30 s
    assert not factory.pin(17).state
    assert query_one("SELECT state FROM alarm_activations WHERE id = ?", (second["activation_id"],))["state"] == "completada"


def test_pin_ocupado_pasa_a_error_sin_fingir_simulacion(mock_pi):
    ctrl, factory = mock_pi
    other = DigitalOutputDevice(17)  # otro "proceso" ya usa el pin
    try:
        ctrl.setup(17, 27)
        assert ctrl.mode == "error" and "en uso" in ctrl.error
        r = ctrl.trigger("alto", CFG, source="deteccion")  # nunca lanza: el reconocimiento sigue
        assert r["state"] == "error"
        assert query_one("SELECT state FROM alarm_activations WHERE id = ?", (r["activation_id"],))["state"] == "error"
    finally:
        other.close()


def test_fallo_al_escribir_no_rompe_y_se_registra(mock_pi, monkeypatch):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)

    class Broken:
        def __setattr__(self, k, v):
            raise OSError("cable suelto")

        def close(self):
            pass

    ctrl._buzzer = Broken()
    r = ctrl.trigger("alto", CFG, source="prueba")
    assert _wait(lambda: not ctrl.alarm_active, 3)
    assert "cable suelto" in ctrl.error and not factory.pin(17).state
    assert query_one("SELECT state FROM alarm_activations WHERE id = ?", (r["activation_id"],))["state"] == "error"


def test_configuracion_desactiva_salidas_y_nivel_minimo(mock_pi):
    ctrl, _ = mock_pi
    ctrl.setup(17, 27)
    assert ctrl.trigger("alto", {**CFG, "gpio_enabled": False}, source="deteccion")["state"] == "desactivada"
    r = ctrl.trigger("bajo", {**CFG, "buzzer_min_level": "medio"}, source="deteccion")
    assert r["led"] is True and r["buzzer"] is False
    ctrl.silence()
    assert ctrl.trigger("alto", {**CFG, "led_enabled": False, "buzzer_enabled": False}, source="deteccion")["state"] == "desactivada"


def test_cerrar_apaga_y_libera(mock_pi):
    ctrl, factory = mock_pi
    ctrl.setup(17, 27)
    ctrl.trigger("alto", {**CFG, "led_seconds": 30, "buzzer_seconds": 30}, source="prueba")
    assert _wait(lambda: bool(factory.pin(17).state))
    ctrl.close()
    assert not factory.pin(17).state and not factory.pin(27).state
    DigitalOutputDevice(17).close()  # el pin quedó libre


def test_reinicio_inesperado_cierra_activaciones_huerfanas(client):
    from app.core.database import execute, utcnow
    aid = execute("INSERT INTO alarm_activations (at, source, mode, state) VALUES (?, 'deteccion', 'hardware', 'activa')",
                  (utcnow(),))
    assert AlarmController.recover_interrupted() >= 1
    assert query_one("SELECT state FROM alarm_activations WHERE id = ?", (aid,))["state"] == "error"


def test_validacion_de_pines(client):
    r = client.put("/api/settings", json={"led_pin": 2})
    assert r.status_code == 422 and "GPIO2" in r.json()["detail"]
    assert client.put("/api/settings", json={"buzzer_pin": 17}).status_code == 422  # mismo pin que el LED
    assert client.put("/api/settings", json={"buzzer_type": "otro"}).status_code == 422
    r = client.put("/api/settings", json={"led_seconds": 5, "buzzer_seconds": 3, "buzzer_type": "activo"})
    assert r.status_code == 200


def test_valores_por_defecto_solicitados():
    from app.services.settings_store import DEFAULTS
    assert (DEFAULTS["led_pin"], DEFAULTS["buzzer_pin"]) == (17, 27)
    assert (DEFAULTS["led_seconds"], DEFAULTS["buzzer_seconds"]) == (5, 3)
    assert (DEFAULTS["confirm_frames"], DEFAULTS["dedup_seconds"]) == (3, 15)
    assert DEFAULTS["buzzer_pattern"] == "intermitente"


# ------------------------------------------------------------- API y diagnóstico
def test_api_estado_e_historial(client):
    st = client.get("/api/hardware").json()
    assert st["status"]["led_physical"] == 11 and st["status"]["buzzer_physical"] == 13
    assert {"bcm": 17, "physical": 11} in st["safe_pins"] and len(st["tests"]) == 5
    hist = client.get("/api/hardware/activations").json()
    assert "items" in hist and hist["total"] >= 0


@pytest.mark.parametrize("name", ["led", "buzzer", "completa"])
def test_pruebas_1_a_3(client, name):
    r = client.post(f"/api/hardware/test/{name}").json()
    assert r["ok"], r
    client.post("/api/hardware/silence")


def test_prueba_4_blacklist_activa_salidas_y_registra(client):
    settings.update({"alerts_enabled": True, "gpio_enabled": True, "led_enabled": True, "buzzer_enabled": True})
    r = client.post("/api/hardware/test/blacklist").json()
    assert r["ok"], r
    ev = query_one("SELECT * FROM events WHERE uid = ?", (r["details"]["event_uid"],))
    assert ev["type"] == "coincidencia" and ev["is_simulated"] == 1 and ev["alarm_state"] in ("activada", "simulada")
    act = query("SELECT * FROM alarm_activations WHERE event_id = ?", (ev["id"],))
    assert act and act[0]["source"] == "simulada" and act[0]["led"] == 1 and act[0]["buzzer"] == 1
    client.post("/api/hardware/silence")


def test_prueba_4_falla_con_alertas_desactivadas(client):
    settings.update({"alerts_enabled": False})
    try:
        r = client.post("/api/hardware/test/blacklist").json()
        assert not r["ok"] and r["hint"]
    finally:
        settings.update({"alerts_enabled": True})


def test_prueba_5_desconocido_no_activa(client):
    before = alarm.trigger_count
    r = client.post("/api/hardware/test/desconocido").json()
    assert r["ok"], r
    assert alarm.trigger_count == before


def test_alerta_real_guarda_estado_de_alarma(client):
    """Ruta de producción: _maybe_alert registra la alerta y luego activa la alarma."""
    import numpy as np
    from app.services.face_engine import Face
    from app.services.pipeline import pipeline

    face = Face(box=(10, 10, 50, 50), score=0.9, raw=np.zeros(15, np.float32))
    face.match = {"entry_id": None, "uid": "FG-ALARM", "name": "Alarma", "level": "alto", "score": 0.7}
    row = pipeline._maybe_alert(np.zeros((240, 320, 3), np.uint8), face, settings.all(), simulated=True, force=True)
    assert row["alarm_state"] in ("activada", "simulada")
    assert query_one("SELECT alarm_state FROM events WHERE id = ?", (row["id"],))["alarm_state"] == row["alarm_state"]
    alarm.silence()


def test_permisos(client):
    from tests.conftest import make_user
    op = make_user(client, "op_alarma", "operator")
    assert op.post("/api/hardware/silence").status_code == 200   # el operador puede silenciar
    assert op.post("/api/hardware/test/led").status_code == 403  # pero no probar ni configurar
    assert op.get("/api/hardware").status_code == 403
    aud = make_user(client, "aud_alarma", "auditor")
    assert aud.post("/api/hardware/silence").status_code == 403
