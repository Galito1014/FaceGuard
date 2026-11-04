from datetime import datetime, timedelta, timezone

from app.core.database import execute, query_one


def test_recheck_interval_respeta_el_rango(client):
    assert client.put("/api/settings", json={"recheck_interval_ms": 0}).status_code == 200
    assert client.put("/api/settings", json={"recheck_interval_ms": 10000}).status_code == 200
    assert client.put("/api/settings", json={"recheck_interval_ms": 10001}).status_code == 422
    client.put("/api/settings", json={"recheck_interval_ms": 1000})


def test_configuracion_valida_e_invalida(client):
    assert client.put("/api/settings", json={"match_threshold": 0.5}).status_code == 200
    assert client.get("/api/settings").json()["values"]["match_threshold"] == 0.5
    assert client.put("/api/settings", json={"match_threshold": 5}).status_code == 422
    assert client.put("/api/settings", json={"led_pin": 17, "buzzer_pin": 17}).status_code == 422
    assert client.put("/api/settings", json={"desconocido": 1}).status_code == 422
    client.put("/api/settings", json={"match_threshold": 0.42})


def test_retencion_borra_eventos_y_vence_registros(client):
    old = (datetime.now(timezone.utc) - timedelta(days=400)).replace(microsecond=0).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    execute("INSERT INTO events (uid, occurred_at, camera, type, message) VALUES ('EV-OLD', ?, 'CAM', 'deteccion', 'viejo')", (old,))
    execute("INSERT INTO events (uid, occurred_at, camera, type, review_status, message) "
            "VALUES ('EV-OLD-PEND', ?, 'CAM', 'coincidencia', 'pendiente', 'pendiente vieja')", (old,))
    eid = execute("INSERT INTO blacklist (uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at, updated_at) "
                  "VALUES ('FG-EXP', 'Vencido', 'r', 'l', 'bajo', ?, ?, ?)", (old, past, old))
    r = client.post("/api/system/retention/run").json()
    assert r["events_deleted"] >= 1 and r["entries_expired"] >= 1
    assert query_one("SELECT id FROM events WHERE uid='EV-OLD'") is None
    assert query_one("SELECT id FROM events WHERE uid='EV-OLD-PEND'") is not None  # pendientes se conservan
    assert query_one("SELECT status FROM blacklist WHERE id=?", (eid,))["status"] == "vencido"
    client.delete(f"/api/blacklist/{eid}")
