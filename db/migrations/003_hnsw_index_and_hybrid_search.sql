-- Migration: HNSW index + hybrid search function
-- Date: 2026-05-19

CREATE INDEX IF NOT EXISTS price_records_embedding_hnsw
  ON price_records USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE OR REPLACE FUNCTION search_hybrid(
  q_embedding vector,
  q_text      text,
  top_k       int DEFAULT 20,
  w_cosine    float DEFAULT 0.5,
  w_trigram   float DEFAULT 0.3,
  w_tsvector  float DEFAULT 0.2
) RETURNS TABLE (
  id bigint, nama text, merek text, spesifikasi text, satuan text,
  harga numeric, supplier text, effective_date date, sumber text, category text,
  score float, cosine_sim float, trigram_sim float, ts_rank float
) LANGUAGE sql STABLE AS $$
  WITH candidates AS (
    SELECT
      p.id, p.nama, p.merek, p.spesifikasi, p.satuan,
      p.harga, p.supplier, p.effective_date, p.sumber, p.category,
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
         harga, supplier, effective_date, sumber, category,
         (w_cosine * cosine_sim + w_trigram * trigram_sim + w_tsvector * ts_rank)::float AS score,
         cosine_sim::float, trigram_sim::float, ts_rank::float
  FROM candidates
  ORDER BY score DESC
  LIMIT top_k;
$$;
