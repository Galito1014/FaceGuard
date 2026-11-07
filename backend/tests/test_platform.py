"""Compatibilidad multiplataforma (Raspberry Pi OS / Windows 10-11)."""
import cv2

from app.core import compat
from app.services import camera as camera_mod
from app.services import system_monitor
from app.services.alarm_controller import AlarmController


def test_backends_linux_igual_que_antes(monkeypatch):
    monkeypatch.delenv("FACEGUARD_CAMERA_BACKEND", raising=False)
    monkeypatch.setattr(compat, "os_name", lambda: "linux")
    assert compat.camera_backends(cv2) == [("v4l2", cv2.CAP_V4L2)]


def test_backends_windows_dshow_luego_msmf(monkeypatch):
    monkeypatch.delenv("FACEGUARD_CAMERA_BACKEND", raising=False)
    monkeypatch.setattr(compat, "os_name", lambda: "windows")
    names = [n for n, _ in compat.camera_backends(cv2)]
    assert names == ["dshow", "msmf", "any"]


def test_backend_forzado(monkeypatch):
    monkeypatch.setenv("FACEGUARD_CAMERA_BACKEND", "msmf")
    assert compat.camera_backends(cv2) == [("msmf", cv2.CAP_MSMF)]


def test_gpio_simulado_fuera_de_linux(monkeypatch):
    monkeypatch.setattr(compat, "gpio_supported", lambda: False)
    g = AlarmController()
    g.setup(17, 27)
    st = g.status()
    assert st["simulated"] and st["mode"] == "simulado" and "simulado" in st["error"]
    r = g.trigger("alto", {"gpio_enabled": True, "led_enabled": True, "buzzer_enabled": True, "buzzer_min_level": "medio",
                           "led_seconds": 1, "buzzer_seconds": 1, "buzzer_pattern": "continuo"}, source="prueba")
    assert (r["led"], r["buzzer"], r["state"]) == (True, True, "simulada")
    g.close()


def test_listado_por_sondeo_sin_camaras(monkeypatch):
    """Ruta de Windows: sin /dev/video* se prueban índices con OpenCV."""
    class FakeCap:
        def __init__(self, idx, api):
            self.idx = idx
        def isOpened(self):
            return self.idx == 1
        def release(self):
            pass
    monkeypatch.setattr(compat, "IS_LINUX", False)
    monkeypatch.setattr(compat, "os_name", lambda: "windows")
    monkeypatch.setattr(compat, "camera_prefix", lambda: "Cámara ")
    monkeypatch.setattr(camera_mod.cv2, "VideoCapture", FakeCap)
    monkeypatch.setattr(camera_mod, "_probe_cache", (0.0, []))
    devices = camera_mod.list_cameras()
    assert [d["index"] for d in devices] == [1]
    assert devices[0]["path"] == "Cámara 1"


def test_monitor_sistema_no_falla(client):
    snap = system_monitor.snapshot()
    assert snap["disk_percent"] >= 0 and len(snap["load_avg"]) == 3
    assert system_monitor.info()["os_family"] == compat.os_name()
    r = client.get("/api/settings").json()
    assert r["camera_prefix"] in ("/dev/video", "Cámara ")
    assert "device" in client.get("/api/camera/status").json()["camera"]


def test_env_file(tmp_path, monkeypatch):
    from app.config import load_env_file
    f = tmp_path / ".env"
    f.write_text('# comentario\nFACEGUARD_TEST_X="hola"\nFACEGUARD_TEST_Y=ya\n', encoding="utf-8")
    monkeypatch.delenv("FACEGUARD_TEST_X", raising=False)
    monkeypatch.setenv("FACEGUARD_TEST_Y", "existente")
    load_env_file(f)
    import os
    assert os.environ["FACEGUARD_TEST_X"] == "hola"
    assert os.environ["FACEGUARD_TEST_Y"] == "existente"  # nunca reemplaza el entorno
    monkeypatch.delenv("FACEGUARD_TEST_X")
