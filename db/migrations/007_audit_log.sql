-- Migration 007: audit_log table (Task 3.7)
-- Date: 2026-05-19

CREATE TABLE IF NOT EXISTS audit_log (
    id           bigserial PRIMARY KEY,
    at           timestamptz NOT NULL DEFAULT now(),
    actor        text NOT NULL,
    action       text NOT NULL,
    entity_type  text NOT NULL,
    entity_id    bigint,
    before       jsonb,
    after        jsonb
);

CREATE INDEX IF NOT EXISTS audit_log_at_idx ON audit_log (at DESC);
CREATE INDEX IF NOT EXISTS audit_log_entity_idx ON audit_log (entity_type, entity_id);
