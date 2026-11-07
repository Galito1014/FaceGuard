"""Asistente de primer uso, restricción de redes y comprobación de versiones.

El asistente necesita una instalación sin usuarios, así que esas pruebas corren
en un proceso aparte con su propia carpeta de datos (la sesión de pruebas
principal ya tiene un administrador creado).
"""
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from app.core.network import ip_allowed, is_loopback, parse_networks
from app.services.updates import is_newer, parse_version

BACKEND = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ redes
@pytest.mark.parametrize("ip,ok", [
    ("127.0.0.1", True), ("::1", True), ("192.168.1.20", True), ("10.0.0.5", True), ("172.20.3.4", True),
    ("fe80::1", True), ("::ffff:192.168.0.7", True),
    ("8.8.8.8", False), ("200.1.2.3", False), ("2001:4860::8888", False), ("172.32.0.1", False),
    ("testclient", False), (None, False),
])
def test_red_local_por_defecto(ip, ok):
    assert ip_allowed(ip, parse_networks("local")) is ok


def test_solo_loopback_y_lista_explicita():
    assert is_loopback("127.0.0.1") and not is_loopback("192.168.1.2")
    nets = parse_networks("192.168.50.0/24")
    assert ip_allowed("192.168.50.9", nets) and ip_allowed("127.0.0.1", nets)
    assert not ip_allowed("192.168.1.9", nets)
    assert parse_networks("all") is None and ip_allowed("8.8.8.8", None)


def test_middleware_rechaza_ip_publica(client, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main_module
    monkeypatch.setattr(main_module, "ALLOWED_NETWORKS", parse_networks("local"))
    assert TestClient(main_module.app, client=("8.8.8.8", 4000)).get("/api/health").status_code == 403
    assert TestClient(main_module.app, client=("192.168.1.30", 4000)).get("/api/health").status_code == 200


# ------------------------------------------------------------ versiones
def test_comparacion_de_versiones():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert is_newer("v1.10.0", "1.9.9") and not is_newer("v1.1.0", "1.1.0") and not is_newer("1.0.9", "1.1.0")
    assert parse_version("v2.0.0-beta.1") == (2, 0, 0)


def test_actualizaciones_desactivadas_por_defecto(client):
    r = client.get("/api/system/update")
    assert r.status_code == 200
    assert r.json()["enabled"] is False and r.json()["update_available"] is False


def test_setup_no_disponible_si_ya_hay_usuarios(client):
    assert client.get("/api/setup/status").json()["needs_setup"] is False
    r = client.post("/api/setup", json={"username": "otro", "full_name": "X", "password": "OtraClave2026",
                                        "privacy_ack": True})
    assert r.status_code == 409


# ------------------------------------------------- asistente (proceso aparte)
SCRIPT = textwrap.dedent('''
    import sys
    sys.path.insert(0, ".")
    import app.main as m
    from fastapi.testclient import TestClient
    m.ALLOWED_NETWORKS = None
    from app.config import config

    lan = TestClient(m.app, client=("192.168.1.50", 5000))
    local = TestClient(m.app, client=("127.0.0.1", 5000))
    with lan:
        st = lan.get("/api/setup/status").json()
        assert st["needs_setup"] and st["code_required"], st
        assert local.get("/api/setup/status").json()["code_required"] is False
        assert lan.get("/api/auth/me").status_code == 401
        code = (config.secret_dir / "setup_code.txt").read_text().strip()
        body = {"username": "dueno", "full_name": "Dueño", "password": "ClaveSegura2026", "privacy_ack": True,
                "settings": {"camera_index": 1, "match_threshold": 0.45, "update_check": False}}
        # Sin código o con código incorrecto desde la LAN: rechazado
        assert lan.post("/api/setup", json=body).status_code == 403
        assert lan.post("/api/setup", json={**body, "setup_code": "AAAAAAAA"}).status_code == 403
        # Sin aceptar el aviso de privacidad / contraseña débil / parámetro no permitido
        assert lan.post("/api/setup", json={**body, "setup_code": code, "privacy_ack": False}).status_code == 400
        assert lan.post("/api/setup", json={**body, "setup_code": code, "password": "corta"}).status_code == 400
        bad = {**body, "setup_code": code, "settings": {"demo_mode": True}}
        assert lan.post("/api/setup", json=bad).status_code == 400
        # Correcto: crea el superadministrador, aplica la configuración e inicia sesión
        r = lan.post("/api/setup", json={**body, "setup_code": f"{code[:4]}-{code[4:].lower()}"})
        assert r.status_code == 200, r.text
        me = lan.get("/api/auth/me").json()
        assert me["role"] == "superadmin" and me["must_change_password"] is False
        cfg = lan.get("/api/settings").json()
        values = cfg.get("values", cfg)
        assert values["camera_index"] == 1 and values["match_threshold"] == 0.45
        assert not (config.secret_dir / "setup_code.txt").exists()
        # Ya no se puede repetir
        assert local.post("/api/setup", json=body).status_code == 409
        actions = [a["action"] for a in lan.get("/api/audit").json()["items"]]
        assert "configuración inicial completada" in actions
    print("OK")
''')


def test_asistente_primer_uso():
    with tempfile.TemporaryDirectory(prefix="faceguard-setup-") as tmp:
        env = {k: v for k, v in os.environ.items() if k != "FACEGUARD_ADMIN_PASSWORD"}
        env.update(FACEGUARD_DATA_DIR=tmp, FACEGUARD_DISABLE_WORKERS="1", FACEGUARD_ENV_FILE=os.path.join(tmp, "none.env"))
        res = subprocess.run([sys.executable, "-c", SCRIPT], cwd=BACKEND, env=env, capture_output=True, text=True,
                             timeout=120)
        assert res.returncode == 0 and "OK" in res.stdout, res.stdout[-2000:] + res.stderr[-3000:]


def test_reduccion_por_temperatura():
    from app.services.pipeline import thermal_factor
    assert thermal_factor(None) == 1.0 and thermal_factor(60) == 1.0
    assert thermal_factor(76) == 1.5 and thermal_factor(82.5) == 2.0
