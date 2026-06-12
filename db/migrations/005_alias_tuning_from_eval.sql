-- Migration 005: additional aliases tuned from Phase 1 eval failures
-- Date: 2026-05-19

INSERT INTO alias (variant, canonical, kind, confidence, created_by) VALUES
    ('kabel berisolasi pvc fleksibel', 'kabel nymhy', 'material', 0.8, 'tune-eval-2026-05-19'),
    ('kabel berisolasi fleksibel', 'kabel nymhy', 'material', 0.8, 'tune-eval-2026-05-19'),
    ('kabel 3 inti', 'kabel nym', 'material', 0.6, 'tune-eval-2026-05-19'),
    ('pengkabelan panel', 'kabel nym', 'material', 0.5, 'tune-eval-2026-05-19')
ON CONFLICT (variant, kind) DO UPDATE SET canonical = EXCLUDED.canonical;
