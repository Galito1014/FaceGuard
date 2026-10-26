"""Acceso a SQLite y sistema de migraciones versionadas.

Cada archivo `backend/migrations/NNN_nombre.sql` se aplica una sola vez, en
orden, y queda registrado en la tabla `schema_migrations`. Para una futura
actualización basta con agregar `002_algo.sql`.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import BASE_DIR, config

log = logging.getLogger("faceguard.db")
MIGRATIONS_DIR = BASE_DIR / "migrations"
_write_lock = threading.RLock()


def utcnow() -> str:
    """Marca de tiempo ISO-8601 en UTC con precisión de segundos."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.db_path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")      # lecturas concurrentes, menos desgaste de la SD
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Conexión de corta duración. Hace commit al salir sin error."""
    conn = _connect()
    try:
        with _write_lock:
            yield conn
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with get_db() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute(sql, params).fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple | dict = ()) -> int:
    """Ejecuta una sentencia y devuelve lastrowid."""
    with get_db() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid


def run_migrations(db_path: Path | None = None) -> list[str]:
    applied: list[str] = []
    conn = _connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = file.stem
            if version in done:
                continue
            log.info("Aplicando migración %s", version)
            conn.executescript(file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (version, utcnow()))
            conn.commit()
            applied.append(version)
    finally:
        conn.close()
    return applied
