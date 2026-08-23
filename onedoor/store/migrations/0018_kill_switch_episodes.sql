-- ND-052 / S2, R045 §5's second requirement. The kill switch does not block
-- ratification -- so the LIFT is where the pen's work must be shown.
--
-- The reasoning, recorded because the table makes no sense without it: the switch wins
-- over every action under every policy, so nothing ratified can move while it holds.
-- Blocking ratification would punish the legitimate operator tightening rules
-- mid-incident, while an attacker with ratification access never needed the incident.
-- The moment of risk is not the ratification; it is the moment the door opens again.
--
-- So: record the active `version_hash` when the switch is ENGAGED, and let the release
-- path report any change since -- *"the rules changed while the door was shut, from X
-- to Y"* -- so the human lifting the switch does so knowing. Surfaced and recorded; the
-- lift is not blocked either. This product makes states visible; it does not take the
-- wheel.
--
-- An EPISODE rather than a config key, so the history survives the next engagement.
-- A single overwritten value would answer "what happened last time" and erase
-- "what happened the time before", and an incident review needs both.
--
--   version_hash_at_engagement  NULLABLE, and null does NOT mean "no change". It means
--                               the store had recorded no policy version when the
--                               switch was engaged, so a comparison is not available.
--                               The release path reports that as `undeterminable`,
--                               never folded into `unchanged` -- unverifiable and
--                               absent are not each other, and neither is a pass.
--
--   released_at                 NULL while the episode is open. At most one open
--                               episode exists at a time: engaging an already-engaged
--                               switch does not start a second one, because the door
--                               has been shut since the FIRST engagement and that is
--                               the moment the comparison must run from.
--
-- Deliberately NOT append-only: an episode is closed by writing `released_at`, which
-- is the one update this table exists to allow. What must not be revisable is the
-- receipt that cites it, and that lives in `ratifications`.

CREATE TABLE IF NOT EXISTS kill_switch_episodes (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    engaged_at                 TEXT NOT NULL,
    origin                     TEXT NOT NULL,
    version_hash_at_engagement TEXT,
    released_at                TEXT,
    version_hash_at_release    TEXT
);

CREATE INDEX IF NOT EXISTS kill_switch_episodes_open
ON kill_switch_episodes(released_at);
