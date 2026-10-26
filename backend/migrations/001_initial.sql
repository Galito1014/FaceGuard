-- FaceGuard AI · Migración 001 · Esquema inicial

CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name       TEXT    NOT NULL,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('superadmin','admin','operator','auditor')),
    active          INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    last_login      TEXT
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash  TEXT    NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL,
    ip          TEXT,
    user_agent  TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

-- Lista de alerta (blacklist). Fotografía y plantilla biométrica se guardan cifradas.
CREATE TABLE blacklist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uid             TEXT    NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    info            TEXT    NOT NULL DEFAULT '',
    reason          TEXT    NOT NULL,
    legal_basis     TEXT    NOT NULL,
    alert_level     TEXT    NOT NULL CHECK (alert_level IN ('bajo','medio','alto')),
    registered_at   TEXT    NOT NULL,
    expires_at      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'activo' CHECK (status IN ('activo','inactivo','vencido')),
    notes           TEXT    NOT NULL DEFAULT '',
    photo_file      TEXT,
    embedding_enc   BLOB,
    photo_quality   TEXT,
    created_by      INTEGER REFERENCES users(id),
    updated_at      TEXT    NOT NULL,
    is_simulated    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_blacklist_status ON blacklist(status);

CREATE TABLE blacklist_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL REFERENCES blacklist(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(id),
    username    TEXT,
    action      TEXT    NOT NULL,
    changes     TEXT    NOT NULL DEFAULT '{}',
    at          TEXT    NOT NULL
);
CREATE INDEX idx_bl_history_entry ON blacklist_history(entry_id);

-- Eventos: detecciones, coincidencias (alertas), capturas y eventos de sistema.
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uid             TEXT    NOT NULL UNIQUE,
    occurred_at     TEXT    NOT NULL,
    camera          TEXT    NOT NULL,
    type            TEXT    NOT NULL CHECK (type IN ('deteccion','coincidencia','captura','sistema')),
    entry_id        INTEGER REFERENCES blacklist(id) ON DELETE SET NULL,
    entry_name      TEXT,
    score           REAL,
    level           TEXT,
    faces_count     INTEGER NOT NULL DEFAULT 0,
    review_status   TEXT    CHECK (review_status IN ('pendiente','confirmada','falso_positivo','cerrada')),
    reviewed_by     INTEGER REFERENCES users(id),
    reviewer_name   TEXT,
    reviewed_at     TEXT,
    notes           TEXT    NOT NULL DEFAULT '',
    message         TEXT    NOT NULL DEFAULT '',
    snapshot_file   TEXT,
    is_simulated    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_events_time   ON events(occurred_at);
CREATE INDEX idx_events_type   ON events(type);
CREATE INDEX idx_events_review ON events(review_status);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT    NOT NULL,
    user_id     INTEGER,
    username    TEXT,
    action      TEXT    NOT NULL,
    target      TEXT    NOT NULL DEFAULT '',
    details     TEXT    NOT NULL DEFAULT '',
    ip          TEXT
);
CREATE INDEX idx_audit_time ON audit_log(at);

CREATE TABLE settings (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
