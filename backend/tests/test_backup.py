"""Respaldo y restauración de la base de datos y los archivos cifrados."""
import json
import sqlite3
import zipfile
from dataclasses import replace

import pytest
import shutil

from app.services import backup


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    from app.config import config
    new = replace(config, data_dir=tmp_path / "data")
    new.secret_dir.mkdir(parents=True)
    (new.media_dir / "photos").mkdir(parents=True)
    (new.secret_dir / "fernet.key").write_bytes(b"clave-a")
    (new.media_dir / "photos" / "a.bin").write_bytes(b"foto")
    db = sqlite3.connect(new.db_path)
    db.execute("CREATE TABLE t (v TEXT)")
    db.execute("INSERT INTO t VALUES ('original')")
    db.commit()
    db.close()
    monkeypatch.setattr(backup, "config", new)
    return new


def _value(cfg):
    db = sqlite3.connect(cfg.db_path)
    try:
        return db.execute("SELECT v FROM t").fetchone()[0]
    finally:
        db.close()


def _change(cfg):
    db = sqlite3.connect(cfg.db_path)
    db.execute("UPDATE t SET v = 'cambiado'")
    db.commit()
    db.close()
    (cfg.media_dir / "photos" / "a.bin").write_bytes(b"otra")
    (cfg.media_dir / "photos" / "nueva.bin").write_bytes(b"x")


def test_respaldo_no_incluye_la_clave_por_defecto(cfg, tmp_path):
    path = backup.create_backup(tmp_path / "bk")
    names = zipfile.ZipFile(path).namelist()
    assert "faceguard.db" in names and "media/photos/a.bin" in names
    assert not any("fernet" in n for n in names)


def test_restaurar_devuelve_datos_y_guarda_copia_previa(cfg, tmp_path):
    path = backup.create_backup(tmp_path / "bk")
    _change(cfg)
    previous = backup.restore_backup(path)
    assert _value(cfg) == "original"
    assert (cfg.media_dir / "photos" / "a.bin").read_bytes() == b"foto"
    assert not (cfg.media_dir / "photos" / "nueva.bin").exists()
    assert (previous / "media" / "photos" / "nueva.bin").exists()


def test_restaurar_con_otra_clave_se_rechaza(cfg, tmp_path):
    path = backup.create_backup(tmp_path / "bk")
    (cfg.secret_dir / "fernet.key").write_bytes(b"clave-b")
    _change(cfg)
    with pytest.raises(backup.BackupError, match="clave"):
        backup.restore_backup(path)
    assert _value(cfg) == "cambiado"


def test_respaldo_con_clave_restaura_la_clave(cfg, tmp_path):
    path = backup.create_backup(tmp_path / "bk", include_key=True)
    (cfg.secret_dir / "fernet.key").write_bytes(b"clave-b")
    backup.restore_backup(path)
    assert (cfg.secret_dir / "fernet.key").read_bytes() == b"clave-a"


def test_rutas_peligrosas_en_el_zip_se_rechazan(cfg, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": 1}))
        z.writestr("faceguard.db", b"x")
        z.writestr("../../evil.txt", b"x")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad)
    assert _value(cfg) == "original"


def test_base_de_datos_danada_no_reemplaza_la_actual(cfg, tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": 1}))
        z.writestr("faceguard.db", b"no es una base de datos")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad)
    assert _value(cfg) == "original"


def _state(cfg):
    return _value(cfg), (cfg.media_dir / "photos" / "a.bin").read_bytes(), (cfg.secret_dir / "fernet.key").read_bytes()


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
def test_fallo_durante_el_cambio_deja_todo_como_estaba(cfg, tmp_path, monkeypatch, fail_at):
    path = backup.create_backup(tmp_path / "bk", include_key=True)
    _change(cfg)
    (cfg.secret_dir / "fernet.key").write_bytes(b"clave-actual")
    before = _state(cfg)
    real, calls = shutil.move, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError(28, "sin espacio")
        return real(src, dst)
    monkeypatch.setattr(backup.shutil, "move", flaky)
    with pytest.raises(backup.BackupError):
        backup.restore_backup(path)
    monkeypatch.setattr(backup.shutil, "move", real)
    assert _state(cfg) == before
    assert not list(cfg.data_dir.glob("pre-restore-*"))


@pytest.mark.parametrize("name", ["media/photos/..", "media/photos/x\n", "media/photos/a.txt", "media/otros/a.bin"])
def test_nombres_de_archivo_no_validos_se_rechazan(cfg, tmp_path, name):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": 1}))
        z.writestr("faceguard.db", b"x")
        z.writestr(name, b"x")
    with pytest.raises(backup.BackupError):
        backup.restore_backup(bad)
    assert _value(cfg) == "original"


def test_respaldo_es_privado_y_un_fallo_no_deja_archivo(cfg, tmp_path, monkeypatch):
    import os
    path = backup.create_backup(tmp_path / "bk")
    if os.name == "posix":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    path.unlink()
    monkeypatch.setattr(backup.zipfile.ZipFile, "writestr", lambda *a, **k: (_ for _ in ()).throw(OSError("fallo")))
    with pytest.raises(OSError):
        backup.create_backup(tmp_path / "bk")
    assert list((tmp_path / "bk").iterdir()) == []
