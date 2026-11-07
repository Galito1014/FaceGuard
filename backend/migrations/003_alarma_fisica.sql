-- FaceGuard AI · Migración 003 · Alarma física (LED rojo y buzzer)
-- Cada alerta guarda en qué estado quedó la alarma física, y cada activación
-- del LED/buzzer (detección real, alerta simulada o prueba manual) queda en un
-- historial propio, consultable desde Configuración → Hardware & Alarm Settings.

ALTER TABLE events ADD COLUMN alarm_state TEXT;

CREATE TABLE alarm_activations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    at              TEXT    NOT NULL,
    source          TEXT    NOT NULL CHECK (source IN ('deteccion','simulada','prueba')),
    event_id        INTEGER REFERENCES events(id) ON DELETE SET NULL,
    entry_name      TEXT,
    level           TEXT,
    led             INTEGER NOT NULL DEFAULT 0,
    buzzer          INTEGER NOT NULL DEFAULT 0,
    led_seconds     INTEGER,
    buzzer_seconds  INTEGER,
    mode            TEXT    NOT NULL,   -- hardware | simulado | error
    state           TEXT    NOT NULL CHECK (state IN ('activa','completada','silenciada','error')),
    ended_at        TEXT,
    silenced_by     TEXT,
    error           TEXT
);
CREATE INDEX idx_alarm_activations_at ON alarm_activations(at);
