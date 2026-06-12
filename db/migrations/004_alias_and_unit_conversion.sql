-- Migration 004: alias and unit_conversion tables for normalization
-- Date: 2026-05-19

-- ──────────────────────────────────────────────────────────────────
-- alias: variant text → canonical text mapping
-- Used at search_text generation time to collapse spelling/format variants
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alias (
    id          bigserial PRIMARY KEY,
    variant     text NOT NULL,
    canonical   text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('material', 'unit', 'brand')),
    confidence  float NOT NULL DEFAULT 1.0,
    created_by  text,
    created_at  timestamptz DEFAULT now(),
    UNIQUE(variant, kind)
);

CREATE INDEX IF NOT EXISTS alias_variant_trgm
    ON alias USING gin (variant gin_trgm_ops);

CREATE INDEX IF NOT EXISTS alias_canonical_idx
    ON alias (canonical, kind);


-- ──────────────────────────────────────────────────────────────────
-- unit_conversion: from_unit → canonical to_unit with multiplier
-- "1 from_unit = factor * to_unit"
-- material_kind NULL = universal conversion; otherwise scoped
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS unit_conversion (
    id            bigserial PRIMARY KEY,
    from_unit     text NOT NULL,
    to_unit       text NOT NULL,
    factor        numeric NOT NULL,
    material_kind text,
    notes         text,
    UNIQUE (from_unit, to_unit, material_kind)
);


-- ──────────────────────────────────────────────────────────────────
-- SEED: common Indonesian material name variants
-- ──────────────────────────────────────────────────────────────────

-- Material kind aliases (cable types)
INSERT INTO alias (variant, canonical, kind, confidence, created_by) VALUES
    -- Cable type abbreviations
    ('kbl', 'kabel', 'material', 1.0, 'seed'),
    ('cable', 'kabel', 'material', 1.0, 'seed'),
    ('kable', 'kabel', 'material', 0.95, 'seed'),

    -- Cable function paraphrases (semantic)
    ('kabel listrik', 'kabel nya', 'material', 0.6, 'seed'),
    ('kawat instalasi', 'kabel nya', 'material', 0.7, 'seed'),
    ('kabel grounding tunggal', 'kabel nya', 'material', 0.8, 'seed'),
    ('kabel tanam', 'kabel nyy', 'material', 0.8, 'seed'),
    ('kabel outdoor', 'kabel nyy', 'material', 0.7, 'seed'),
    ('kabel armoured', 'kabel nyfgby', 'material', 0.9, 'seed'),
    ('kabel berlapis baja', 'kabel nyfgby', 'material', 0.9, 'seed'),
    ('kabel fleksibel', 'kabel nymhy', 'material', 0.8, 'seed'),

    -- Steel/rebar (besi beton) — anticipating future data
    ('besi ulir', 'besi beton ulir', 'material', 0.95, 'seed'),
    ('besi polos', 'besi beton polos', 'material', 0.95, 'seed'),
    ('rebar', 'besi beton ulir', 'material', 0.9, 'seed'),
    ('bjtd', 'besi beton ulir', 'material', 0.9, 'seed'),
    ('bjtp', 'besi beton polos', 'material', 0.9, 'seed'),

    -- Cement / Semen
    ('semen pc', 'semen portland', 'material', 1.0, 'seed'),
    ('pc', 'semen portland', 'material', 0.7, 'seed'),

    -- Pipe / Pipa
    ('pipa air', 'pipa pvc', 'material', 0.7, 'seed'),
    ('pipa pralon', 'pipa pvc', 'material', 0.95, 'seed'),
    ('pipa paralon', 'pipa pvc', 'material', 0.95, 'seed')
ON CONFLICT (variant, kind) DO NOTHING;


-- Unit aliases
INSERT INTO alias (variant, canonical, kind, confidence, created_by) VALUES
    ('m', 'meter', 'unit', 1.0, 'seed'),
    ('mtr', 'meter', 'unit', 1.0, 'seed'),
    ('m.', 'meter', 'unit', 1.0, 'seed'),
    ('m1', 'meter', 'unit', 1.0, 'seed'),

    ('btg', 'batang', 'unit', 1.0, 'seed'),
    ('bt', 'batang', 'unit', 1.0, 'seed'),
    ('bar', 'batang', 'unit', 1.0, 'seed'),

    ('kg', 'kilogram', 'unit', 1.0, 'seed'),
    ('kilo', 'kilogram', 'unit', 1.0, 'seed'),

    ('pcs', 'pieces', 'unit', 1.0, 'seed'),
    ('pc', 'pieces', 'unit', 1.0, 'seed'),
    ('biji', 'pieces', 'unit', 1.0, 'seed'),
    ('buah', 'pieces', 'unit', 1.0, 'seed'),

    ('sak', 'sak', 'unit', 1.0, 'seed'),
    ('zak', 'sak', 'unit', 1.0, 'seed'),
    ('bag', 'sak', 'unit', 0.9, 'seed'),

    ('lbr', 'lembar', 'unit', 1.0, 'seed'),
    ('sheet', 'lembar', 'unit', 1.0, 'seed'),

    ('m2', 'meter persegi', 'unit', 1.0, 'seed'),
    ('m²', 'meter persegi', 'unit', 1.0, 'seed'),
    ('sqm', 'meter persegi', 'unit', 1.0, 'seed'),

    ('m3', 'meter kubik', 'unit', 1.0, 'seed'),
    ('m³', 'meter kubik', 'unit', 1.0, 'seed'),

    ('dus', 'dus', 'unit', 1.0, 'seed'),
    ('box', 'dus', 'unit', 0.9, 'seed'),
    ('kotak', 'dus', 'unit', 0.9, 'seed'),

    ('rol', 'roll', 'unit', 1.0, 'seed'),
    ('gulung', 'roll', 'unit', 1.0, 'seed')
ON CONFLICT (variant, kind) DO NOTHING;


-- Brand aliases (common typos / casing)
INSERT INTO alias (variant, canonical, kind, confidence, created_by) VALUES
    ('eterna', 'eterna', 'brand', 1.0, 'seed'),
    ('supreme', 'supreme', 'brand', 1.0, 'seed'),
    ('kabelindo', 'kabelindo', 'brand', 1.0, 'seed'),
    ('kbi', 'kabelindo', 'brand', 0.9, 'seed')
ON CONFLICT (variant, kind) DO NOTHING;


-- ──────────────────────────────────────────────────────────────────
-- SEED: unit conversions to canonical units
-- ──────────────────────────────────────────────────────────────────

INSERT INTO unit_conversion (from_unit, to_unit, factor, material_kind, notes) VALUES
    -- Rebar/steel: standard bar length 12m (Indonesian standard)
    ('batang', 'meter', 12, 'besi beton ulir', 'BJTD standard bar length 12m'),
    ('batang', 'meter', 12, 'besi beton polos', 'BJTP standard bar length 12m'),
    ('btg', 'meter', 12, 'besi beton ulir', 'alias short form'),
    ('btg', 'meter', 12, 'besi beton polos', 'alias short form'),

    -- Cement: standard sack is 50kg, but PPC is 40kg
    ('sak', 'kilogram', 50, 'semen portland', 'PC standard 50kg/sack'),
    ('sak', 'kilogram', 40, 'semen ppc', 'PPC standard 40kg/sack'),

    -- Cable rolls (variable, will need product-specific conversion later)
    ('roll', 'meter', 100, 'kabel', 'typical 100m roll — varies by brand'),
    ('gulung', 'meter', 100, 'kabel', 'alias for roll'),

    -- Universal trivial conversions
    ('meter', 'meter', 1, NULL, 'identity'),
    ('kilogram', 'kilogram', 1, NULL, 'identity'),
    ('pieces', 'pieces', 1, NULL, 'identity'),

    -- Box conversions (require product-specific override)
    ('dus', 'pieces', 50, 'keramik 40x40', 'typical 50pcs/dus — override per product')
ON CONFLICT (from_unit, to_unit, material_kind) DO NOTHING;
