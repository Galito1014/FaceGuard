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
    eid = execute("INSERT INTO persons (uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at, updated_at) "
                  "VALUES ('FG-EXP', 'Vencido', 'r', 'l', 'bajo', ?, ?, ?)", (old, past, old))
    r = client.post("/api/system/retention/run").json()
    assert r["events_deleted"] >= 1 and r["entries_expired"] >= 1
    assert query_one("SELECT id FROM events WHERE uid='EV-OLD'") is None
    assert query_one("SELECT id FROM events WHERE uid='EV-OLD-PEND'") is not None  # pendientes se conservan
    assert query_one("SELECT status FROM persons WHERE id=?", (eid,))["status"] == "vencido"
    client.delete(f"/api/persons/{eid}")


def test_retencion_borra_archivos_huerfanos_antiguos(client):
    import os
    import time
    from app.config import config
    from app.services.retention import run_retention
    old = config.media_dir / "photos" / "huerfano.bin"
    new = config.media_dir / "photos" / "reciente.bin"
    from app.core.database import execute, utcnow
    old.write_bytes(b"x"); new.write_bytes(b"x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    execute("INSERT INTO events (uid, occurred_at, camera, type, snapshot_file) VALUES ('EV-REF', ?, 'c', 'sistema', 'snapshots/ref.bin')", (utcnow(),))
    run_retention()
    assert not old.exists() and new.exists()
    new.unlink()
    execute("DELETE FROM events WHERE uid = 'EV-REF'")


def _old_media(n):
    import os
    import time
    from app.config import config
    files = [config.media_dir / "photos" / f"viejo{i}.bin" for i in range(n)]
    past = time.time() - 7200
    for f in files:
        f.write_bytes(b"x")
        os.utime(f, (past, past))
    return files


def test_base_sin_referencias_no_borra_las_imagenes(client):
    """Una base vacía o equivocada no prueba que los archivos sobren."""
    from app.core.database import execute
    from app.services.retention import run_retention
    execute("DELETE FROM persons")
    execute("UPDATE events SET snapshot_file = NULL")
    files = _old_media(3)
    assert run_retention()["orphans_deleted"] == 0
    assert all(f.exists() for f in files)
    for f in files:
        f.unlink()


def test_no_borra_si_la_mayoria_de_archivos_parecen_huerfanos(client):
    from app.core.database import execute, utcnow
    from app.services.retention import run_retention
    execute("INSERT INTO events (uid, occurred_at, camera, type, snapshot_file) VALUES ('EV-R2', ?, 'c', 'sistema', 'snapshots/ref.bin')", (utcnow(),))
    files = _old_media(8)
    assert run_retention()["orphans_deleted"] == 0
    assert all(f.exists() for f in files)
    for f in files:
        f.unlink()
    execute("DELETE FROM events WHERE uid = 'EV-R2'")


def test_fallo_al_limpiar_no_impide_recargar_la_galeria(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.core.database import execute, utcnow
    from app.services import retention
    from app.services.face_engine import gallery
    now = utcnow()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    execute("""INSERT INTO persons (uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at, updated_at)
               VALUES ('FG-VENCE','V','r','l','bajo',?,?,?)""", (now, past, now))
    version = gallery.version
    monkeypatch.setattr(retention, "_remove_orphans", lambda: (_ for _ in ()).throw(OSError("fallo")))
    retention.run_retention()
    assert gallery.version > version
    execute("DELETE FROM persons WHERE uid = 'FG-VENCE'")


def test_opciones_de_sonido_y_almacenamiento(client):
    assert client.put("/api/settings", json={"alert_sound": False}).status_code == 200
    assert client.get("/api/settings").json()["values"]["alert_sound"] is False
    client.put("/api/settings", json={"alert_sound": True})
    storage = client.get("/api/system/info").json()["storage"]
    assert storage["db_path"].endswith("faceguard.db") and "free_gb" in storage


def test_disco_lleno_da_mensaje_comprensible(client, monkeypatch):
    import errno
    from app.api import persons
    def boom(*a, **k):
        raise OSError(errno.ENOSPC, "No space left")
    monkeypatch.setattr(persons, "read_photo", boom)
    r = client.post("/api/persons/validate-photo", files={"photo": ("a.jpg", b"x", "image/jpeg")})
    assert r.status_code == 507 and "espacio" in r.json()["detail"].lower()
