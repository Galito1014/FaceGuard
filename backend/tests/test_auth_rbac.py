from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_user


def test_login_incorrecto_intentos_ilimitados(client):
    c = TestClient(app)
    for _ in range(10):  # sin bloqueo ni espera por defecto
        assert c.post("/api/auth/login", json={"username": "nadie", "password": "x"}).status_code == 401


def test_bloqueo_opcional(client, monkeypatch):
    from app.core.security import throttle
    monkeypatch.setattr(throttle, "MAX_ATTEMPTS", 5)
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"username": "otro", "password": "x"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "otro", "password": "x"}).status_code == 429
    throttle.reset("otro", "testclient")


def test_rutas_privadas_sin_sesion(client):
    c = TestClient(app)
    for path in ("/api/dashboard/summary", "/api/persons", "/api/events", "/api/users", "/api/camera/stream"):
        assert c.get(path).status_code == 401


def test_contrasena_debil_rechazada(client):
    r = client.post("/api/users", json={"username": "debil", "full_name": "Débil", "role": "operator", "password": "123"})
    assert r.status_code == 422


def test_cambio_obligatorio_de_contrasena(client):
    client.post("/api/users", json={"username": "nuevo", "full_name": "Nuevo", "role": "admin", "password": "Inicial12345"})
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "nuevo", "password": "Inicial12345"})
    r = c.get("/api/dashboard/summary")
    assert r.status_code == 403 and "contraseña" in r.json()["detail"]


def test_permisos_por_rol(client):
    auditor = make_user(client, "auditor1", "auditor")
    operador = make_user(client, "operador1", "operator")
    # Auditor: consulta, sin modificar
    assert auditor.get("/api/events").status_code == 200
    assert auditor.get("/api/audit").status_code == 200
    assert auditor.get("/api/persons").status_code == 200
    assert auditor.delete("/api/persons/1").status_code == 403
    assert auditor.get("/api/camera/status").status_code == 403
    assert auditor.post("/api/alerts/1/review", json={"status": "cerrada"}).status_code == 403
    # Operador: monitoreo y alertas, sin lista ni configuración
    assert operador.get("/api/camera/status").status_code == 200
    assert operador.get("/api/alerts").status_code == 200
    assert operador.get("/api/persons").status_code == 403
    assert operador.put("/api/settings", json={"match_threshold": 0.5}).status_code == 403
    assert operador.get("/api/users").status_code == 403


def test_no_eliminar_ultimo_superadmin(client):
    me = client.get("/api/auth/me").json()
    assert client.delete(f"/api/users/{me['id']}").status_code == 409
    assert client.put(f"/api/users/{me['id']}", json={"role": "operator"}).status_code == 409


def test_auditoria_registra_acciones(client):
    rows = client.get("/api/audit?q=sesión").json()["items"]
    assert any(r["action"] == "inicio de sesión" for r in rows)
    assert any(r["action"] == "inicio de sesión fallido" for r in rows)
