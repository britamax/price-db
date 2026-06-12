-- Migration: add embedding columns to price_records
-- Date: 2026-05-19
-- Requires: pgvector extension

ALTER TABLE price_records
  ADD COLUMN IF NOT EXISTS embedding vector(768),
  ADD COLUMN IF NOT EXISTS embedding_model varchar(64),
  ADD COLUMN IF NOT EXISTS embedding_version varchar(16),
  ADD COLUMN IF NOT EXISTS embedded_at timestamptz;

-- Trigram index on search_text (may already exist from v1)
CREATE INDEX IF NOT EXISTS price_records_search_text_trgm
  ON price_records USING gin (search_text gin_trgm_ops);

-- Immutable wrapper for unaccent (needed for index expressions)
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
  RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $func$
  SELECT public.unaccent('unaccent', $1)
$func$;

-- Full-text search index
CREATE INDEX IF NOT EXISTS price_records_search_text_tsv
  ON price_records USING gin (to_tsvector('simple', immutable_unaccent(coalesce(search_text,''))));
