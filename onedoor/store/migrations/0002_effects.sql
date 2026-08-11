-- Effect labels: aliasing-resistant governance. Policies may declare effects;
-- effect_policies hold effect-level tier floors and shared caps. Effect cap
-- counters reuse cap_counters with the key "effect:<name>".
ALTER TABLE policies ADD COLUMN effects_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE policies ADD COLUMN param_effects_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE effect_policies (
    effect TEXT PRIMARY KEY,
    min_tier INTEGER,
    caps_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
