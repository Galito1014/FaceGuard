"""Respaldo y restauración de la base de datos y los archivos cifrados.

Un respaldo es un .zip con la base de datos, las fotos y capturas cifradas y un
manifiesto. La clave de cifrado queda fuera por defecto: sin ella los archivos
no se pueden leer, así que guardarla junto a ellos anularía el cifrado.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import config

log = logging.getLogger("faceguard.backup")

FORMAT = 1
DB_NAME = "faceguard.db"
KEY_NAME = "secret/fernet.key"
_SAFE_MEDIA = re.compile(r"media/(photos|snapshots)/[A-Za-z0-9_-]+\.bin")


class BackupError(Exception):
    """El respaldo no se puede usar. El mensaje es apto para mostrarlo."""


def _key_file() -> Path:
    return config.secret_dir / "fernet.key"


def _fingerprint(key: bytes | None) -> str | None:
    return hashlib.sha256(key).hexdigest()[:16] if key else None


def _current_fingerprint() -> str | None:
    path = _key_file()
    return _fingerprint(path.read_bytes()) if path.exists() else None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def create_backup(dest_dir: Path, include_key: bool = False) -> Path:
    if not config.db_path.exists():
        raise BackupError("No existe una base de datos para respaldar.")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"faceguard-respaldo-{_timestamp()}.zip"
    # Se escribe en una carpeta privada: un fallo no deja un .zip legible a medias.
    with tempfile.TemporaryDirectory(dir=dest_dir) as tmp:
        snapshot = Path(tmp) / DB_NAME
        partial = Path(tmp) / target.name
        source = sqlite3.connect(config.db_path)
        copy = sqlite3.connect(snapshot)
        try:
            source.backup(copy)  # copia coherente aunque el sistema esté en uso
        finally:
            copy.close()
            source.close()
        manifest = {"format": FORMAT, "created_at": datetime.now().astimezone().isoformat(),
                    "app_version": config.version, "key_fingerprint": _current_fingerprint(), "includes_key": include_key}
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.write(snapshot, DB_NAME)
            for sub in ("photos", "snapshots"):
                folder = config.media_dir / sub
                if folder.exists():
                    for f in sorted(folder.glob("*.bin")):
                        z.write(f, f"media/{sub}/{f.name}")
            if include_key:
                z.write(_key_file(), KEY_NAME)
        os.chmod(partial, 0o600)
        os.replace(partial, target)
    log.info("Respaldo creado: %s", target)
    return target


def _read_manifest(z: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(z.read("manifest.json"))
    except (KeyError, ValueError) as exc:
        raise BackupError("El archivo no es un respaldo de FaceGuard.") from exc
    if manifest.get("format") != FORMAT:
        raise BackupError("Formato de respaldo no compatible.")
    return manifest


def _check_names(names: list[str]) -> None:
    allowed = {"manifest.json", DB_NAME, KEY_NAME}
    for name in names:
        if name not in allowed and not _SAFE_MEDIA.fullmatch(name):
            raise BackupError(f"El respaldo contiene una ruta no permitida: {name}")
    if DB_NAME not in names:
        raise BackupError("El respaldo no contiene la base de datos.")


def _check_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise BackupError("La base de datos del respaldo está dañada.") from exc
    finally:
        conn.close()
    if result != "ok":
        raise BackupError("La base de datos del respaldo está dañada.")


def _swap(staging: Path, has_key: bool) -> Path:
    """Instala lo validado. Si un paso falla, deshace todos los anteriores."""
    previous = config.data_dir / f"pre-restore-{_timestamp()}"
    previous.mkdir()
    (previous / "secret").mkdir()
    for sub in ("photos", "snapshots"):
        (staging / "media" / sub).mkdir(parents=True, exist_ok=True)
    steps: list[tuple[Path, Path]] = [(config.media_dir, previous / "media")]
    if has_key:
        steps += [(_key_file(), previous / "secret" / "fernet.key"), (staging / KEY_NAME, _key_file())]
    steps.append((staging / "media", config.media_dir))
    # La base de datos va al final: sin ella en su lugar el sistema no arranca bien.
    for suffix in ("", "-wal", "-shm"):
        current = Path(f"{config.db_path}{suffix}")
        steps.append((current, previous / current.name))
    steps.append((staging / DB_NAME, config.db_path))

    done: list[tuple[Path, Path]] = []
    try:
        for source, target in steps:
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                done.append((source, target))
    except OSError as exc:
        try:
            for source, target in reversed(done):
                shutil.move(str(target), str(source))
        except OSError:
            log.critical("No se pudo deshacer la restauración. Datos anteriores en %s", previous)
            raise BackupError(f"La restauración falló a medias. Los datos anteriores están en {previous}.") from exc
        shutil.rmtree(previous, ignore_errors=True)
        raise BackupError("No se pudo completar la restauración. Los datos actuales no cambiaron.") from exc
    if has_key:
        os.chmod(_key_file(), 0o600)
    return previous


def restore_backup(path: Path) -> Path:
    """Valida el respaldo y lo instala. Devuelve la carpeta con los datos anteriores.

    Nada de los datos actuales se toca hasta que el respaldo pasa todas las
    comprobaciones. El sistema debe estar detenido.
    """
    path = Path(path)
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError("No se pudo abrir el respaldo.") from exc
    with archive as z:
        manifest = _read_manifest(z)
        names = z.namelist()
        _check_names(names)
        has_key = KEY_NAME in names
        with tempfile.TemporaryDirectory(dir=config.data_dir) as tmp:
            staging = Path(tmp)
            try:
                z.extractall(staging)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise BackupError("El respaldo está dañado.") from exc
            _check_database(staging / DB_NAME)
            if not has_key and manifest.get("key_fingerprint") != _current_fingerprint():
                raise BackupError("La clave de cifrado de este equipo no coincide con la del respaldo. "
                                  "Copie la clave original o use un respaldo creado con --with-key.")
            previous = _swap(staging, has_key)
    log.warning("Respaldo restaurado desde %s; datos anteriores en %s", path, previous)
    return previous
