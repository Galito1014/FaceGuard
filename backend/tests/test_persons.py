"""Personas, muestras faciales, clasificación y galería con varias plantillas."""
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import config
from app.core.crypto import encrypt_embedding
from app.core import database
from app.core.database import MIGRATIONS_DIR, execute, query, query_one, utcnow
from app.services.face_engine import MODEL_VERSION, gallery

HAS_MODELS = config.detector_model.exists() and config.recognizer_model.exists()
FUTURE = "2099-01-01"


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).normal(size=128).astype(np.float32)
    return v / np.linalg.norm(v)


def _near(vec: np.ndarray, target_sim: float, seed: int = 99) -> np.ndarray:
    """Vector unitario con la similitud indicada respecto a `vec`."""
    noise = _unit(seed)
    noise -= (noise @ vec) * vec
    noise /= np.linalg.norm(noise)
    out = target_sim * vec + np.sqrt(1 - target_sim ** 2) * noise
    return out.astype(np.float32)


def _person(name: str, classification: str, *vectors: np.ndarray) -> int:
    now = utcnow()
    pid = execute(
        """INSERT INTO persons (uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at,
             classification, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (f"T-{name}", name, "prueba", "prueba", "medio", now, "2099-01-01T00:00:00+00:00", classification, now))
    for i, vec in enumerate(vectors):
        execute("""INSERT INTO face_samples (person_id, photo_file, embedding_enc, model_version, is_primary, created_at)
                   VALUES (?,?,?,?,?,?)""", (pid, f"photos/{name}{i}.bin", encrypt_embedding(vec), MODEL_VERSION, int(i == 0), now))
    return pid


@pytest.fixture
def clean(client):
    execute("DELETE FROM persons")
    gallery.load()
    yield
    execute("DELETE FROM persons")
    gallery.load()


def _jpeg(img) -> bytes:
    return cv2.imencode(".jpg", img)[1].tobytes()


def _face():
    skimage = pytest.importorskip("skimage.data")
    return cv2.cvtColor(skimage.astronaut(), cv2.COLOR_RGB2BGR)


def _form(**extra):
    return {"full_name": "Prueba", "reason": "Prueba automática", "legal_basis": "Imagen de dominio público",
            "alert_level": "alto", "expires_at": FUTURE, **extra}


# ----------------------------------------------------------------- migración
def test_migracion_conserva_registros_fotos_y_alertas(tmp_path):
    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript((MIGRATIONS_DIR / "001_initial.sql").read_text(encoding="utf-8"))
    db.execute("""INSERT INTO blacklist (id, uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at,
                  photo_file, embedding_enc, photo_quality, updated_at)
                  VALUES (7,'FG-1','Ana','r','l','alto','t','2099','photos/a.bin',x'01','{}','t')""")
    db.execute("INSERT INTO blacklist_history (entry_id, action, at) VALUES (7,'creado','t')")
    db.execute("INSERT INTO events (uid, occurred_at, camera, type, entry_id) VALUES ('E1','t','c','coincidencia',7)")
    db.commit()

    db.executescript("BEGIN;" + (MIGRATIONS_DIR / "002_persons.sql").read_text(encoding="utf-8") + "COMMIT;")

    assert db.execute("SELECT full_name, classification FROM persons WHERE id=7").fetchone() == ("Ana", "no_autorizada")
    assert db.execute("""SELECT photo_file, embedding_enc, model_version, is_primary FROM face_samples
                         WHERE person_id=7""").fetchone() == ("photos/a.bin", b"\x01", "sface_2021dec", 1)
    assert db.execute("SELECT action FROM person_history WHERE entry_id=7").fetchone() == ("creado",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.execute("DELETE FROM persons WHERE id=7")
    assert db.execute("SELECT COUNT(*) FROM face_samples").fetchone() == (0,)
    assert db.execute("SELECT entry_id FROM events WHERE uid='E1'").fetchone() == (None,)
    db.close()


def _old_database(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    db.executescript((MIGRATIONS_DIR / "001_initial.sql").read_text(encoding="utf-8"))
    db.execute("INSERT INTO schema_migrations VALUES ('001_initial', 't')")
    db.execute("""INSERT INTO blacklist (uid, full_name, reason, legal_basis, alert_level, registered_at, expires_at, updated_at)
                  VALUES ('FG-1','Ana','r','l','alto','t','2099','t')""")
    db.commit()
    db.close()


def test_migracion_y_su_registro_son_atomicos(tmp_path, monkeypatch):
    """Un corte entre la migración y su registro no debe impedir el arranque."""
    path = tmp_path / "old.db"
    _old_database(path)
    monkeypatch.setattr(database, "utcnow", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("corte")))
    with pytest.raises(sqlite3.OperationalError):
        database.run_migrations(path)
    monkeypatch.undo()
    assert database.run_migrations(path) == ["002_persons", "003_alarma_fisica"]
    db = sqlite3.connect(path)
    assert db.execute("SELECT full_name FROM persons").fetchone() == ("Ana",)
    db.close()


def test_fallo_en_medio_de_una_migracion_no_cambia_nada(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    _old_database(path)
    bad = tmp_path / "migrations"
    bad.mkdir()
    (bad / "001_initial.sql").write_text("", encoding="utf-8")
    (bad / "002_mala.sql").write_text("ALTER TABLE blacklist RENAME TO x; SELECT * FROM no_existe;", encoding="utf-8")
    monkeypatch.setattr(database, "MIGRATIONS_DIR", bad)
    with pytest.raises(sqlite3.OperationalError):
        database.run_migrations(path)
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM blacklist").fetchone() == (1,)
    db.close()


def test_copia_automatica_antes_de_migrar(tmp_path):
    path = tmp_path / "old.db"
    _old_database(path)
    database.run_migrations(path)
    copies = list(tmp_path.glob("old.db.antes-de-*"))
    assert len(copies) == 1
    db = sqlite3.connect(copies[0])
    assert db.execute("SELECT full_name FROM blacklist").fetchone() == ("Ana",)
    db.close()


def test_base_nueva_no_crea_copia(tmp_path):
    database.run_migrations(tmp_path / "nueva.db")
    assert not list(tmp_path.glob("*.antes-de-*"))


# ------------------------------------------------------------------- galería
def test_varias_plantillas_cuentan_como_una_persona(clean):
    a, b = _unit(1), _unit(2)
    pid = _person("Ana", "no_autorizada", a, b)
    gallery.load()
    assert gallery.size == 1 and gallery.templates == 2
    meta, sim = gallery.best_match(b)
    assert meta["entry_id"] == pid and sim > 0.99


def test_autorizada_parecida_no_oculta_coincidencia_con_blacklist(clean):
    vec = _unit(3)
    _person("Autorizada", "autorizada", vec)
    bl = _person("Blacklist", "no_autorizada", _near(vec, 0.6))
    gallery.load()
    meta, sim = gallery.best_match(vec, threshold=0.42)
    assert meta["entry_id"] == bl and sim == pytest.approx(0.6, abs=1e-3)


def test_blacklist_bajo_el_umbral_no_desplaza_a_la_autorizada(clean):
    vec = _unit(4)
    aut = _person("Autorizada", "autorizada", vec)
    _person("Blacklist", "no_autorizada", _near(vec, 0.3))
    gallery.load()
    assert gallery.best_match(vec, threshold=0.42)[0]["entry_id"] == aut


def test_otra_version_de_modelo_no_entra_en_la_galeria(clean):
    pid = _person("Ana", "no_autorizada", _unit(5))
    execute("UPDATE face_samples SET model_version = 'otro' WHERE person_id = ?", (pid,))
    gallery.load()
    assert gallery.size == 0


def test_top_matches_agrupa_por_persona(clean):
    vec = _unit(6)
    a = _person("A", "no_autorizada", vec, _near(vec, 0.8, 7))
    b = _person("B", "autorizada", _near(vec, 0.5, 8))
    _person("C", "autorizada", _near(vec, 0.1, 9))
    gallery.load()
    assert [m["entry_id"] for m in gallery.top_matches(vec, 0.42)] == [a, b]


def test_top_matches_conserva_blacklist_aunque_haya_tres_autorizadas_mejores(clean):
    vec = _unit(20)
    for i, sim in enumerate((0.9, 0.85, 0.8)):
        _person(f"A{i}", "autorizada", _near(vec, sim, 30 + i))
    bl = _person("B", "no_autorizada", _near(vec, 0.7, 40))
    gallery.load()
    assert bl in [m["entry_id"] for m in gallery.top_matches(vec, 0.42)]


# ----------------------------------------------------------------------- API
def test_autorizada_exige_consentimiento(client, clean):
    data = {"full_name": "Eva", "classification": "autorizada", "expires_at": FUTURE}
    files = {"photo": ("a.jpg", b"\xff\xd8\xff", "image/jpeg")}
    r = client.post("/api/persons", data=data, files=files)
    assert r.status_code == 422 and "consentimiento" in r.json()["detail"].lower()


def test_no_autorizada_exige_motivo_y_base_legal(client, clean):
    r = client.post("/api/persons", data={"full_name": "X", "expires_at": FUTURE, "alert_level": "alto"},
                    files={"photo": ("a.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert r.status_code == 422


def test_filtra_por_clasificacion_y_estadisticas(client, clean):
    _person("Ana", "no_autorizada", _unit(10))
    _person("Eva", "autorizada", _unit(11))
    r = client.get("/api/persons", params={"classification": "autorizada"}).json()
    assert [i["full_name"] for i in r["items"]] == ["Eva"]
    assert r["items"][0]["template_count"] == 1


def test_cambiar_a_no_autorizada_exige_motivo_propio(client, clean):
    pid = _person("Eva", "autorizada", _unit(12))
    r = client.put(f"/api/persons/{pid}", data={"classification": "no_autorizada"})
    assert r.status_code == 422
    r = client.put(f"/api/persons/{pid}", data={"classification": "no_autorizada", "reason": "Incidente documentado",
                                                "legal_basis": "Acta 12", "alert_level": "alto"})
    assert r.status_code == 200 and r.json()["classification"] == "no_autorizada"
    assert gallery.best_match(_unit(12))[0]["classification"] == "no_autorizada"


def test_cambiar_a_autorizada_exige_consentimiento(client, clean):
    pid = _person("Ana", "no_autorizada", _unit(13))
    assert client.put(f"/api/persons/{pid}", data={"classification": "autorizada"}).status_code == 422
    r = client.put(f"/api/persons/{pid}", data={"classification": "autorizada", "consent": "true"})
    assert r.status_code == 200 and r.json()["reason"] == "Persona autorizada"


def test_operador_no_administra_personas(client, clean):
    from tests.conftest import make_user
    op = make_user(client, "operador_personas", "operator")
    assert op.get("/api/persons").status_code == 403
    assert op.post("/api/persons", data={}).status_code == 403


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_duplicado_pide_confirmacion_y_sin_registro_automatico(client, clean):
    img = _jpeg(_face())
    first = client.post("/api/persons", data=_form(), files={"photo": ("a.jpg", img, "image/jpeg")})
    assert first.status_code == 200, first.text
    r = client.post("/api/persons", data=_form(full_name="Otra"), files={"photo": ("a.jpg", img, "image/jpeg")})
    assert r.status_code == 409
    assert r.json()["detail"]["duplicates"][0]["entry_id"] == first.json()["id"]
    assert query_one("SELECT COUNT(*) AS n FROM persons")["n"] == 1
    r = client.post("/api/persons", data=_form(full_name="Otra", confirm_duplicate="true"),
                    files={"photo": ("a.jpg", img, "image/jpeg")})
    assert r.status_code == 200


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_muestras_agregar_principal_eliminar(client, clean):
    img = _face()
    person = client.post("/api/persons", data=_form(), files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")}).json()
    pid = person["id"]
    same = client.post(f"/api/persons/{pid}/samples", files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")})
    assert same.status_code == 409  # la misma fotografía no se repite

    flipped = client.post(f"/api/persons/{pid}/samples", files={"photo": ("b.jpg", _jpeg(cv2.flip(img, 1)), "image/jpeg")})
    assert flipped.status_code == 200, flipped.text
    assert gallery.templates == 2
    samples = client.get(f"/api/persons/{pid}").json()["samples"]
    assert len(samples) == 2 and sum(s["is_primary"] for s in samples) == 1
    assert all("embedding_enc" not in s and "photo_file" not in s for s in samples)

    second = next(s for s in samples if not s["is_primary"])
    assert client.post(f"/api/persons/{pid}/samples/{second['id']}/primary").status_code == 200
    r = client.get(f"/api/persons/{pid}/samples/{second['id']}/photo")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"

    assert client.delete(f"/api/persons/{pid}/samples/{second['id']}").status_code == 200
    remaining = client.get(f"/api/persons/{pid}").json()["samples"]
    assert len(remaining) == 1 and remaining[0]["is_primary"]
    assert client.delete(f"/api/persons/{pid}/samples/{remaining[0]['id']}").status_code == 409  # queda una sola


@pytest.mark.skipif(not HAS_MODELS, reason="modelos no descargados")
def test_eliminar_persona_borra_todos_sus_archivos(client, clean):
    img = _face()
    pid = client.post("/api/persons", data=_form(), files={"photo": ("a.jpg", _jpeg(img), "image/jpeg")}).json()["id"]
    client.post(f"/api/persons/{pid}/samples", files={"photo": ("b.jpg", _jpeg(cv2.flip(img, 1)), "image/jpeg")})
    names = [Path(r["photo_file"]).name for r in query("SELECT photo_file FROM face_samples WHERE person_id = ?", (pid,))]
    assert len(names) == 2
    assert client.delete(f"/api/persons/{pid}").status_code == 200
    on_disk = {f.name for f in (config.media_dir / "photos").glob("*.bin")}
    assert not on_disk & set(names)


def test_fallo_al_borrar_archivo_no_deja_a_la_persona_en_la_galeria(client, clean, monkeypatch):
    pid = _person("Ana", "no_autorizada", _unit(50))
    gallery.load()

    def locked(name):
        raise PermissionError("archivo en uso")
    monkeypatch.setattr("app.services.persons.secure_delete", locked)
    assert client.delete(f"/api/persons/{pid}").status_code == 200
    assert gallery.size == 0
    assert query_one("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1")["action"] == "eliminación de registro"


def test_eliminar_persona_borra_sus_capturas_de_alertas(client, clean):
    from app.core.crypto import save_encrypted_file
    pid = _person("Ana", "no_autorizada", _unit(51))
    snap = save_encrypted_file("snapshots", b"rostro")
    execute("""INSERT INTO events (uid, occurred_at, camera, type, entry_id, entry_name, review_status, snapshot_file)
               VALUES ('EV-DEL', ?, 'c', 'coincidencia', ?, 'Ana', 'pendiente', ?)""", (utcnow(), pid, snap))
    assert client.delete(f"/api/persons/{pid}").status_code == 200
    ev = query_one("SELECT * FROM events WHERE uid = 'EV-DEL'")
    assert ev["snapshot_file"] is None and ev["entry_name"] == "T-Ana" and ev["review_status"] == "cerrada"
    assert not (config.media_dir / snap).exists()


def test_vencer_autorizada_borra_su_biometria_tras_el_plazo(client, clean):
    from datetime import datetime, timedelta, timezone
    from app.services.retention import run_retention
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    a = _person("Antigua", "autorizada", _unit(52))
    b = _person("Reciente", "autorizada", _unit(53))
    c = _person("Blacklist", "no_autorizada", _unit(54))
    execute("UPDATE persons SET expires_at = ?, status = 'vencido' WHERE id IN (?, ?)", (old, a, c))
    execute("UPDATE persons SET expires_at = ?, status = 'vencido' WHERE id = ?", (recent, b))
    assert run_retention()["authorized_purged"] == 1
    ids = {r["id"] for r in query("SELECT id FROM persons")}
    assert ids == {b, c}


def test_jpeg_con_bytes_de_relleno_no_evita_el_limite(client, monkeypatch):
    from app.api import persons
    data = _jpeg(np.full((400, 600, 3), 128, np.uint8))
    tricky = data[:2] + b"\xff" * 4 + data[2:]
    assert persons.image_pixels(tricky) == 240000
    monkeypatch.setattr(persons, "MAX_PIXELS", 100)
    r = client.post("/api/analysis/photo", files={"photo": ("a.jpg", tricky, "image/jpeg")})
    assert r.status_code == 413


def test_jpeg_sin_dimensiones_legibles_se_rechaza(client):
    tricky = b"\xff\xd8\xff\xe0\x00\x00" + b"\x00" * 40
    r = client.post("/api/analysis/photo", files={"photo": ("a.jpg", tricky, "image/jpeg")})
    assert r.status_code == 422
