-- Migration 003: HNSW index + search_hybrid function
-- Date: 2026-05-19
-- Updated: 2026-05-19 — return canonical_unit + price_per_canonical_unit (Task 2.3)

CREATE INDEX IF NOT EXISTS price_records_embedding_hnsw
    ON price_records USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


DROP FUNCTION IF EXISTS search_hybrid(vector, text, int, float, float, float);

CREATE OR REPLACE FUNCTION search_hybrid(
  q_embedding vector,
  q_text      text,
  top_k       int DEFAULT 20,
  w_cosine    float DEFAULT 0.4,
  w_trigram   float DEFAULT 0.6,
  w_tsvector  float DEFAULT 0.0
) RETURNS TABLE (
  id bigint, nama text, merek text, spesifikasi text, satuan text,
  canonical_unit text, harga numeric, price_per_canonical_unit numeric,
  supplier text, effective_date date, sumber text, category text,
  score float, cosine_sim float, trigram_sim float, ts_rank float
) LANGUAGE sql STABLE AS $$
  WITH candidates AS (
    SELECT
      p.id, p.nama, p.merek, p.spesifikasi, p.satuan,
      p.canonical_unit, p.harga, p.price_per_canonical_unit,
      p.supplier, p.effective_date, p.sumber, p.category,
      1 - (p.embedding <=> q_embedding)                                        AS cosine_sim,
      similarity(p.search_text, lower(immutable_unaccent(q_text)))              AS trigram_sim,
      ts_rank(
        to_tsvector('simple', immutable_unaccent(coalesce(p.search_text,''))),
        plainto_tsquery('simple', immutable_unaccent(q_text))
      )                                                                         AS ts_rank
    FROM price_records p
    WHERE p.embedding IS NOT NULL
    ORDER BY p.embedding <=> q_embedding
    LIMIT 200
  )
  SELECT id, nama, merek, spesifikasi, satuan,
         canonical_unit, harga, price_per_canonical_unit,
         supplier, effective_date, sumber, category,
         (w_cosine * cosine_sim + w_trigram * trigram_sim + w_tsvector * ts_rank)::float AS score,
         cosine_sim::float, trigram_sim::float, ts_rank::float
  FROM candidates
  ORDER BY score DESC
  LIMIT top_k;
$$;
