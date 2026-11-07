"""Configuración de pruebas: base de datos temporal y sin hilos de cámara."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="faceguard-test-"))
os.environ["FACEGUARD_DATA_DIR"] = str(TMP)
os.environ["FACEGUARD_DISABLE_WORKERS"] = "1"
os.environ["FACEGUARD_ADMIN_PASSWORD"] = "Temporal12345"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402
from app.main import app  # noqa: E402

# El cliente de pruebas se presenta como "testclient" (no es una IP). La
# restricción de redes se prueba aparte en test_setup_red.py.
main_module.ALLOWED_NETWORKS = None

ADMIN_PW = "SuperClave2026"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"username": "admin", "password": "Temporal12345"})
        assert r.status_code == 200
        r = c.post("/api/auth/change-password", json={"current_password": "Temporal12345", "new_password": ADMIN_PW})
        assert r.status_code == 200
        yield c
    shutil.rmtree(TMP, ignore_errors=True)


def login_as(client_app, username: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def make_user(client, username: str, role: str, password: str = "Inicial12345") -> TestClient:
    r = client.post("/api/users", json={"username": username, "full_name": f"Usuario {role}", "role": role, "password": password})
    assert r.status_code == 200, r.text
    c = login_as(client, username, password)
    new_pw = "Definitiva2026"
    assert c.post("/api/auth/change-password", json={"current_password": password, "new_password": new_pw}).status_code == 200
    return c
