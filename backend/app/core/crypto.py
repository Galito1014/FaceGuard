"""Cifrado de datos biométricos en reposo (fotografías, plantillas y capturas).

Se usa Fernet (AES-128-CBC + HMAC-SHA256) de la biblioteca `cryptography`.
La clave se genera en el primer arranque y se guarda en data/secret/fernet.key
con permisos 600. Sin esa clave, las fotos y plantillas copiadas de la tarjeta
SD no se pueden leer.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet

from app.config import config

_fernet: Fernet | None = None


def _key_path() -> Path:
    return config.secret_dir / "fernet.key"


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        path = _key_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(Fernet.generate_key())
            os.chmod(path, 0o600)
        _fernet = Fernet(path.read_bytes().strip())
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    return get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return get_fernet().decrypt(token)


def encrypt_embedding(vec: np.ndarray) -> bytes:
    return encrypt_bytes(np.asarray(vec, dtype=np.float32).tobytes())


def decrypt_embedding(token: bytes) -> np.ndarray:
    return np.frombuffer(decrypt_bytes(token), dtype=np.float32).copy()


def save_encrypted_file(subdir: str, data: bytes) -> str:
    """Guarda `data` cifrado en media/<subdir>/ y devuelve el nombre relativo."""
    name = f"{subdir}/{secrets.token_hex(16)}.bin"
    path = config.media_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(data))
    os.chmod(path, 0o600)
    return name


def read_encrypted_file(name: str) -> bytes | None:
    path = (config.media_dir / name).resolve()
    if not str(path).startswith(str(config.media_dir.resolve())) or not path.exists():
        return None
    return decrypt_bytes(path.read_bytes())


def secure_delete(name: str | None) -> None:
    """Sobrescribe y elimina un archivo cifrado.

    Nota: en memorias flash (tarjeta SD) la sobrescritura no garantiza el
    borrado físico por el nivelado de desgaste; por eso los archivos ya están
    cifrados y la clave nunca sale del dispositivo.
    """
    if not name:
        return
    path = (config.media_dir / name).resolve()
    if not str(path).startswith(str(config.media_dir.resolve())) or not path.exists():
        return
    try:
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            fh.write(secrets.token_bytes(size))
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        path.unlink(missing_ok=True)
