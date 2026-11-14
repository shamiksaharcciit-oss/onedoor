# Migration upgrade notes

This file is for anyone developing against this repository's own history,
not for a released package — it does not ship in the wheel or the sdist.

## `0050_shadow_decisions_coverage.sql` and a store built from an unreleased
## intermediate head

`0050` adds `coverage`, `live_reason_code` and `comparison` to
`shadow_decisions` by `ALTER TABLE ... ADD COLUMN`. This runs cleanly
against `0049` exactly as this repository ships it today, and against any
store that has never applied `0049` at all.

It does **not** run against a store that applied `0049` while this
repository's own `0049_shadow_decisions.sql` briefly carried one or both
of these columns directly, during the pre-release work that added
shadow-decision coverage tracking. That covers two shapes, not only one: a
store created fresh during that window, **and** a store created at any
earlier point (a released 0.10.2 database among them) whose first open
during that window is simply when its own migration run reached `0049`
and applied that window's shape of it. Either way, the store already has
the `coverage` column (added once shadow-coverage tracking was introduced)
under the filename `0049`, recorded in its own `schema_migrations` table;
`0050`'s own filename has never been claimed, so it still runs, and its
first `ALTER TABLE` then fails with
`OperationalError: duplicate column name: coverage`, since the column is
already there. `Database.init()` raises; the store is left exactly as it
was, with 49 migrations applied — no data is lost or corrupted, the store
simply does not open at a later point.

No release has ever carried any of those shapes of `0049` itself, so this
only affects a database file whose migration history passed through that
pre-release window at the moment it applied `0049` — whenever that store
itself was first created.

**Recovery:** recreate the store (a fresh database file, migrated forward
from nothing). There is no supported in-place upgrade path from one of
these pre-release shapes of `0049`.
