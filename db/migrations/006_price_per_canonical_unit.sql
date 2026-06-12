-- Migration 006: price_per_canonical_unit + canonical_unit auto-compute
-- Date: 2026-05-19

ALTER TABLE price_records
    ADD COLUMN IF NOT EXISTS canonical_unit text,
    ADD COLUMN IF NOT EXISTS price_per_canonical_unit numeric;


-- Helper function: resolve a (raw_unit, material_category) → (canonical_unit, factor)
-- factor: multiply raw price by factor to get canonical price per unit
-- e.g. "btg" rebar (12m bar) at Rp 600,000/btg → factor=1/12, canonical_unit='meter', price=50,000/m
CREATE OR REPLACE FUNCTION resolve_canonical_unit(
    raw_unit text,
    category text
) RETURNS TABLE(canonical_unit text, factor numeric)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    norm_unit text;
    norm_category text;
    rec record;
BEGIN
    -- Normalize inputs via alias table (unit + material)
    norm_unit := lower(coalesce(raw_unit, ''));
    norm_category := lower(coalesce(category, ''));

    -- Resolve unit variant → canonical (e.g. 'm' → 'meter', 'btg' → 'batang')
    SELECT canonical INTO norm_unit
    FROM alias
    WHERE kind = 'unit' AND lower(variant) = norm_unit
    LIMIT 1;
    IF norm_unit IS NULL THEN
        norm_unit := lower(coalesce(raw_unit, ''));
    END IF;

    -- Look up conversion: prefer material-specific, fall back to universal
    -- For matching material_kind, accept exact match OR substring (category contains kind)
    SELECT uc.to_unit, uc.factor INTO rec
    FROM unit_conversion uc
    WHERE uc.from_unit = norm_unit
      AND (
            uc.material_kind IS NOT NULL
            AND norm_category LIKE '%' || lower(uc.material_kind) || '%'
          )
    ORDER BY length(uc.material_kind) DESC NULLS LAST
    LIMIT 1;

    IF rec IS NULL THEN
        -- Try universal (material_kind IS NULL)
        SELECT uc.to_unit, uc.factor INTO rec
        FROM unit_conversion uc
        WHERE uc.from_unit = norm_unit AND uc.material_kind IS NULL
        LIMIT 1;
    END IF;

    IF rec IS NOT NULL THEN
        canonical_unit := rec.to_unit;
        factor := rec.factor;
        RETURN NEXT;
    ELSE
        -- No conversion known: identity
        canonical_unit := norm_unit;
        factor := 1;
        RETURN NEXT;
    END IF;
END;
$$;


-- Function to compute and update one row's canonical fields
CREATE OR REPLACE FUNCTION recompute_canonical_unit_for(row_id bigint)
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    r record;
    res record;
BEGIN
    SELECT id, satuan, category, harga INTO r
    FROM price_records WHERE id = row_id;
    IF r IS NULL THEN RETURN; END IF;

    SELECT canonical_unit, factor INTO res
    FROM resolve_canonical_unit(r.satuan, r.category);

    UPDATE price_records
    SET canonical_unit = res.canonical_unit,
        price_per_canonical_unit = CASE
            WHEN r.harga IS NOT NULL AND res.factor > 0
            THEN r.harga / res.factor
            ELSE NULL
        END
    WHERE id = row_id;
END;
$$;


-- Trigger: auto-recompute on INSERT/UPDATE of relevant fields
CREATE OR REPLACE FUNCTION trg_recompute_canonical_unit()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    res record;
BEGIN
    SELECT canonical_unit, factor INTO res
    FROM resolve_canonical_unit(NEW.satuan, NEW.category);

    NEW.canonical_unit := res.canonical_unit;
    NEW.price_per_canonical_unit := CASE
        WHEN NEW.harga IS NOT NULL AND res.factor > 0
        THEN NEW.harga / res.factor
        ELSE NULL
    END;

    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS price_records_canonical_unit_trg ON price_records;
CREATE TRIGGER price_records_canonical_unit_trg
    BEFORE INSERT OR UPDATE OF satuan, category, harga
    ON price_records
    FOR EACH ROW
    EXECUTE FUNCTION trg_recompute_canonical_unit();


-- Backfill existing rows (must modify a watched column to trigger BEFORE UPDATE)
UPDATE price_records SET harga = harga;


CREATE INDEX IF NOT EXISTS price_records_canonical_unit_idx
    ON price_records (canonical_unit);
