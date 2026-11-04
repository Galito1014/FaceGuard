-- FaceGuard AI · Migración 002 · Personas y muestras faciales
-- La lista de alerta pasa a ser la tabla `persons`, con una clasificación por
-- persona. Fotos y plantillas pasan a `face_samples` para admitir varias por persona.
-- run_migrations la aplica en una sola transacción, junto con su registro.

ALTER TABLE blacklist RENAME TO persons;
ALTER TABLE blacklist_history RENAME TO person_history;

ALTER TABLE persons ADD COLUMN classification TEXT NOT NULL DEFAULT 'no_autorizada'
    CHECK (classification IN ('autorizada','no_autorizada'));

DROP INDEX idx_blacklist_status;
CREATE INDEX idx_persons_classification ON persons(classification, status);
CREATE INDEX idx_persons_name ON persons(full_name);
DROP INDEX idx_bl_history_entry;
CREATE INDEX idx_person_history_entry ON person_history(entry_id);

CREATE TABLE face_samples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    photo_file      TEXT    NOT NULL,
    embedding_enc   BLOB,
    model_version   TEXT,
    quality         TEXT,
    content_hash    TEXT,
    is_primary      INTEGER NOT NULL DEFAULT 0,
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL
);
CREATE INDEX idx_face_samples_person ON face_samples(person_id);
CREATE UNIQUE INDEX idx_face_samples_primary ON face_samples(person_id) WHERE is_primary = 1;
CREATE UNIQUE INDEX idx_face_samples_hash ON face_samples(person_id, content_hash);

INSERT INTO face_samples (person_id, photo_file, embedding_enc, model_version, quality, is_primary, created_by, created_at)
SELECT id, photo_file, embedding_enc,
       CASE WHEN embedding_enc IS NOT NULL THEN 'sface_2021dec' END,
       photo_quality, 1, created_by, registered_at
FROM persons WHERE photo_file IS NOT NULL;

ALTER TABLE persons DROP COLUMN photo_file;
ALTER TABLE persons DROP COLUMN embedding_enc;
ALTER TABLE persons DROP COLUMN photo_quality;
