-- Migration 008: batch_job table for async Excel matching jobs
-- Date: 2026-05-19

CREATE TABLE IF NOT EXISTS batch_job (
    id           bigserial PRIMARY KEY,
    filename     text NOT NULL,
    original_name text NOT NULL,
    name_column  text,
    unit_column  text,
    qty_column   text,
    total_rows   int NOT NULL DEFAULT 0,
    processed    int NOT NULL DEFAULT 0,
    status       text NOT NULL DEFAULT 'pending',  -- pending|running|done|failed|cancelled
    result_path  text,
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz
);

CREATE INDEX IF NOT EXISTS batch_job_status_idx ON batch_job (status, created_at DESC);
