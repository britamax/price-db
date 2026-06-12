-- Migration 009: Source tracking, regional filter, supplier reliability (Phase 5)

-- Supplier profile: reliability metrics per supplier
CREATE TABLE IF NOT EXISTS supplier_profile (
    id                       bigserial PRIMARY KEY,
    supplier_normalized      text NOT NULL UNIQUE,
    display_name             text NOT NULL,
    kota                     text,
    provinsi                 text,
    region                   text,
    sumber_type              text,   -- 'survey','e-katalog','penawaran','manual'
    contact                  text,
    website                  text,
    notes                    text,
    total_records            int NOT NULL DEFAULT 0,
    last_updated             date,
    update_count             int NOT NULL DEFAULT 0,
    avg_update_interval_days numeric,
    reliability_score        numeric GENERATED ALWAYS AS (
        CASE
            WHEN update_count = 0 THEN 0
            WHEN update_count >= 10 THEN 1.0
            ELSE round((update_count::numeric / 10), 2)
        END
    ) STORED,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS supplier_profile_kota_idx     ON supplier_profile(kota);
CREATE INDEX IF NOT EXISTS supplier_profile_region_idx   ON supplier_profile(region);
CREATE INDEX IF NOT EXISTS price_records_lokasi_idx      ON price_records(lokasi);
CREATE INDEX IF NOT EXISTS price_records_sumber_idx      ON price_records(sumber);
CREATE INDEX IF NOT EXISTS price_records_sup_norm_idx    ON price_records(supplier_normalized);
CREATE INDEX IF NOT EXISTS price_records_eff_date_idx    ON price_records(effective_date DESC);

-- Seed existing suppliers. Only Sinar Surabaya Sakti has known location.
INSERT INTO supplier_profile (supplier_normalized, display_name, kota, provinsi, region, sumber_type, total_records, last_updated, update_count)
SELECT
    supplier_normalized,
    MAX(supplier),
    CASE WHEN supplier_normalized = 'sinar surabaya sakti' THEN 'Surabaya' END,
    CASE WHEN supplier_normalized = 'sinar surabaya sakti' THEN 'Jawa Timur' END,
    CASE WHEN supplier_normalized = 'sinar surabaya sakti' THEN 'Jawa Timur' END,
    'penawaran',
    COUNT(*),
    MAX(effective_date),
    COUNT(DISTINCT effective_date)
FROM price_records
WHERE supplier_normalized IS NOT NULL AND supplier_normalized <> ''
GROUP BY supplier_normalized
ON CONFLICT (supplier_normalized) DO NOTHING;

-- Backfill lokasi/sumber from supplier_profile into price_records
UPDATE price_records pr
SET lokasi = COALESCE(NULLIF(sp.kota, ''), sp.provinsi),
    sumber = sp.sumber_type
FROM supplier_profile sp
WHERE pr.supplier_normalized = sp.supplier_normalized
  AND (pr.lokasi IS DISTINCT FROM COALESCE(NULLIF(sp.kota, ''), sp.provinsi)
       OR pr.sumber IS DISTINCT FROM sp.sumber_type);

-- Trigger: auto-refresh supplier metrics on new inserts
CREATE OR REPLACE FUNCTION refresh_supplier_metrics() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO supplier_profile (supplier_normalized, display_name, kota, total_records, last_updated, update_count)
    VALUES (NEW.supplier_normalized, NEW.supplier, NEW.lokasi, 1, NEW.effective_date, 1)
    ON CONFLICT (supplier_normalized) DO UPDATE SET
        total_records = (SELECT COUNT(*) FROM price_records WHERE supplier_normalized = NEW.supplier_normalized),
        last_updated  = GREATEST(supplier_profile.last_updated, NEW.effective_date),
        update_count  = (SELECT COUNT(DISTINCT effective_date) FROM price_records WHERE supplier_normalized = NEW.supplier_normalized),
        updated_at    = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_refresh_supplier ON price_records;
CREATE TRIGGER trg_refresh_supplier
AFTER INSERT ON price_records
FOR EACH ROW EXECUTE FUNCTION refresh_supplier_metrics();

-- View: price_records enriched with supplier metadata
CREATE OR REPLACE VIEW v_price_with_supplier AS
SELECT 
    pr.id, pr.nama, pr.merek, pr.spesifikasi, pr.satuan, pr.category, pr.subcategory,
    pr.harga, pr.harga_raw, pr.supplier, pr.supplier_normalized,
    pr.effective_date, pr.lokasi, pr.sumber, pr.keterangan,
    pr.search_text, pr.canonical_unit, pr.price_per_canonical_unit,
    pr.embedding, pr.created_at,
    sp.kota, sp.provinsi, sp.region, sp.sumber_type,
    sp.reliability_score,
    sp.last_updated   AS supplier_last_updated,
    sp.update_count   AS supplier_update_count
FROM price_records pr
LEFT JOIN supplier_profile sp ON pr.supplier_normalized = sp.supplier_normalized;


-- Search function with optional regional/source/category filters (Phase 5)
DROP FUNCTION IF EXISTS public.search_hybrid(vector, text, integer, double precision, double precision, double precision);
CREATE OR REPLACE FUNCTION public.search_hybrid(
  q_embedding vector,
  q_text text,
  top_k integer DEFAULT 20,
  w_cosine double precision DEFAULT 0.4,
  w_trigram double precision DEFAULT 0.6,
  w_tsvector double precision DEFAULT 0.0,
  p_lokasi text DEFAULT NULL,
  p_sumber text DEFAULT NULL,
  p_category text DEFAULT NULL
)
RETURNS TABLE(id bigint, nama text, merek text, spesifikasi text, satuan text,
              canonical_unit text, harga numeric, price_per_canonical_unit numeric,
              supplier text, lokasi text, effective_date date, sumber text, category text,
              score double precision, cosine_sim double precision,
              trigram_sim double precision, ts_rank double precision)
LANGUAGE sql STABLE AS $function$
  WITH candidates AS (
    SELECT p.id, p.nama, p.merek, p.spesifikasi, p.satuan,
           p.canonical_unit, p.harga, p.price_per_canonical_unit,
           p.supplier, p.lokasi, p.effective_date, p.sumber, p.category,
           1 - (p.embedding <=> q_embedding) AS cosine_sim,
           similarity(p.search_text, lower(immutable_unaccent(q_text))) AS trigram_sim,
           ts_rank(to_tsvector('simple', immutable_unaccent(coalesce(p.search_text,''))),
                   plainto_tsquery('simple', immutable_unaccent(q_text))) AS ts_rank
    FROM price_records p
    WHERE p.embedding IS NOT NULL
      AND (p_lokasi IS NULL OR p.lokasi ILIKE '%' || p_lokasi || '%')
      AND (p_sumber IS NULL OR p.sumber ILIKE '%' || p_sumber || '%')
      AND (p_category IS NULL OR p.category ILIKE p_category)
    ORDER BY p.embedding <=> q_embedding
    LIMIT 200
  )
  SELECT id, nama, merek, spesifikasi, satuan,
         canonical_unit, harga, price_per_canonical_unit,
         supplier, lokasi, effective_date, sumber, category,
         (w_cosine * cosine_sim + w_trigram * trigram_sim + w_tsvector * ts_rank)::float AS score,
         cosine_sim::float, trigram_sim::float, ts_rank::float
  FROM candidates
  ORDER BY score DESC
  LIMIT top_k;
$function$;
