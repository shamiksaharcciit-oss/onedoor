"""The Studio's own store — `studio.db` (ND-052 / S3-T1).

**The enforcer's database contains no row the Studio can edit** (R047 §2). That is the
line this module exists to hold, and it is a sharper line than "the main store is
append-only", which was never true: `policy_current` moves, approvals transition, the
kill switch flips. Mutability already lives in the main store **where the enforcer owns
the mutation**. What that store has never contained is a row a *second process* edits,
and a mutable `policy_candidates` table written by the Studio server would be exactly
that — the proposer holding a standing write path into the enforcer's database, with
SQLite lock contention against `BEGIN IMMEDIATE` as the operational tax on a blurred
boundary.

So drafts live here, beside the canvas that owns them.

What follows from the split, each consequence already paid for
---------------------------------------------------------------
**The ceremony is unaffected.** S1 and S2 take `list[Policy]` *as an argument*, so the
server loads a draft and passes models in memory. No second connection reaches inside
the ceremony, because the ceremony never needed a draft's address — only its content.

**Losing `studio.db` loses drafts and nothing else.** Receipts are evidence and evidence
stays in the enforcer's store, sealed by migrations `0016` and `0017`. The asymmetry is
correct: a draft is working state, and working state that vanishes costs an afternoon,
where evidence that vanishes costs the claim.

**This store carries its own schema version.** The main sequence of numbered migrations
is the *enforcer's* history; `0019` was released back to unclaimed rather than spent on
a table in a different file.

The draft id, and what it is not
---------------------------------
Rows keep a stable `draft_id` so an editor can address the thing it is editing across
page loads. **The digest is never stored as if it were one.** `policy_digest` is
computed from the models at the moment of use, and it is what receipts cite; a draft id
is a handle for editing and travels nowhere. If a stored row and a computed digest ever
disagree, the digest wins — it is the value the evidence carries.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from onedoor.guardrail.models import EffectPolicy, Policy
from onedoor.store.clock import to_iso
from onedoor.store.db import connect
from onedoor.studio import descriptions

SCHEMA_VERSION = 3
"""The Studio store's own version. Not a number from the enforcer's migration sequence.

Version 2 adds S6's `descriptions` and `derivation_records` (see
`studio.descriptions`). Version 3 adds `ND-056`/T2's `state` column, so a draft can be
SUBMITTED for ratification without being ratified. Bumped rather than silently extended:
a store written by version 1 and read by a build expecting version 3 must be
recognisable as such, and `open_store` already refuses a store from the FUTURE for the
same reason.

**No enforcer migration number is claimed** (R047 §2, and `BACKLOG.md`'s register says
`0019`+ is released for exactly this): the main store's numbered migrations are the
enforcer's history, and a column in a different file that a different process owns does
not belong in it. Spending `0019` on one would have written the boundary this split
exists to draw straight back out of the record.
"""

_S6_SCHEMA = descriptions.SCHEMA_SQL

_SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS studio_schema (
    version INTEGER NOT NULL
);

-- Deliberately MUTABLE, and deliberately not in the enforcer's store. Editing is the
-- whole point of a draft: an append-only draft table would seal every keystroke. What
-- must not be revisable is the RECEIPT, and `ratifications` and `backtest_receipts`
-- hold that line in the store where evidence lives.
CREATE TABLE IF NOT EXISTS policy_candidates (
    draft_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    body_json    TEXT NOT NULL,
    base_version TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    -- ND-056/T2, schema 3. `draft` or `submitted`. NULL on rows written before the
    -- column existed, and read as `draft` -- the same absent-value rule the enforcer
    -- uses for an unstamped `protocol`. `submitted` means a human has been ASKED; it
    -- never means anything has been ratified, and no API route can move a draft past it.
    state        TEXT
);
"""
    + _S6_SCHEMA
)


DRAFT = "draft"
SUBMITTED = "submitted"
DRAFT_STATES = (DRAFT, SUBMITTED)
"""What a draft's `state` may be, declared once.

`submitted` means **a human has been asked**, and nothing more. It is not an approval,
it does not move the version pointer, and no route in the v1 API can take a draft past
it — ratification is the ceremony, and the ceremony is a page a person loads.
"""

_ADDED_COLUMNS = {"state": "TEXT"}
"""Columns added after schema 1, applied to an existing store on upgrade.

Declared as data rather than written as a sequence of ALTERs so the upgrade and the
CREATE cannot disagree about what a v3 table has.
"""


class StudioStoreError(RuntimeError):
    """The Studio store could not be opened, or holds a schema this build cannot read."""


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Add any declared column the table does not already have. Idempotent."""
    present = {str(row["name"]) for row in conn.execute("PRAGMA table_info(policy_candidates)")}
    for name, kind in _ADDED_COLUMNS.items():
        if name not in present:
            conn.execute(f"ALTER TABLE policy_candidates ADD COLUMN {name} {kind}")


def open_store(path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) the Studio store at `path`.

    A store written by a newer build is a **refusal**, not a silent downgrade: reading
    unknown rows as if they were the shape this build expects is how a draft turns into
    a candidate nobody authored.

    `check_same_thread=False` is for callers that serialise access with their own lock —
    the Studio server, whose routes FastAPI runs in a threadpool. Passing it without a
    lock would trade a loud `ProgrammingError` for a quiet race, so `StudioState` owns
    both halves together and neither is optional.
    """
    conn = connect(str(path), check_same_thread=check_same_thread)
    try:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT version FROM studio_schema LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO studio_schema (version) VALUES (?)", (SCHEMA_VERSION,))
        elif int(row["version"]) < SCHEMA_VERSION:
            # Forward-only. New TABLES arrive by `IF NOT EXISTS` above, but a new COLUMN
            # does not -- `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already
            # exists, so a v2 store would have kept its old shape while claiming v3.
            # Adding the column explicitly is the upgrade, and it is idempotent because
            # it is guarded by what the table actually has rather than by what the
            # version number says it should.
            _add_missing_columns(conn)
            # Stamped afterwards so a crash between the two leaves the version behind
            # rather than ahead: a store that claims a schema it does not have is the
            # failure direction that hurts.
            conn.execute("UPDATE studio_schema SET version=?", (SCHEMA_VERSION,))
        elif int(row["version"]) > SCHEMA_VERSION:
            raise StudioStoreError(
                f"this studio store was written at schema version {row['version']}, and "
                f"this build reads version {SCHEMA_VERSION}. Reading it anyway would mean "
                "interpreting unknown rows as a shape they were not written in."
            )
    except Exception:
        conn.close()
        raise
    return conn


@dataclass(frozen=True)
class Draft:
    """A candidate being edited, and the version it was pinned to when opened.

    `base_version` is Q3's pin (R047 §3): the canvas diffs against the version it was
    opened on, so a moved active set becomes a **visible state** rather than a picture
    that silently re-bases. `None` means the draft was opened on a store with no
    recorded version — absent, not "unpinned by choice".
    """

    draft_id: str
    title: str
    policies: list[Policy]
    effects: list[EffectPolicy]
    base_version: str | None
    created_at: str
    updated_at: str
    state: str = DRAFT
    """`draft` or `submitted`. A row written before schema 3 has NULL and reads as
    `draft` -- absent means the earliest state, never an unknown one."""

    @property
    def submitted(self) -> bool:
        return self.state == SUBMITTED


def _body(policies: list[Policy], effects: list[EffectPolicy]) -> str:
    return json.dumps(
        {
            "policies": [json.loads(p.model_dump_json()) for p in policies],
            "effects": [json.loads(e.model_dump_json()) for e in effects],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse(row: sqlite3.Row) -> Draft:
    body: dict[str, Any] = json.loads(row["body_json"])
    return Draft(
        draft_id=str(row["draft_id"]),
        title=str(row["title"]),
        policies=[Policy.model_validate(p) for p in body.get("policies", [])],
        effects=[EffectPolicy.model_validate(e) for e in body.get("effects", [])],
        base_version=row["base_version"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        # NULL predates the column, and the earliest state is `draft`. Reading it as
        # anything else would invent a history the row does not have.
        state=str(row["state"]) if _has(row, "state") and row["state"] else DRAFT,
    )


def _has(row: sqlite3.Row, name: str) -> bool:
    return name in row.keys()


def create(
    conn: sqlite3.Connection,
    *,
    title: str,
    policies: list[Policy],
    effects: list[EffectPolicy] | None = None,
    base_version: str | None,
    now: datetime,
    draft_id: str | None = None,
) -> Draft:
    """Start a draft, pinned to the version it was opened against."""
    ident = draft_id or uuid4().hex
    stamp = to_iso(now)
    conn.execute(
        "INSERT INTO policy_candidates "
        "(draft_id, title, body_json, base_version, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (ident, title, _body(policies, list(effects or [])), base_version, stamp, stamp),
    )
    got = load(conn, ident)
    if got is None:  # pragma: no cover - the insert above just wrote it
        raise StudioStoreError(f"draft {ident} did not persist")
    return got


def save(
    conn: sqlite3.Connection,
    draft_id: str,
    *,
    policies: list[Policy],
    effects: list[EffectPolicy] | None = None,
    now: datetime,
    title: str | None = None,
) -> Draft:
    """Overwrite a draft's content. Mutable on purpose; see the module note."""
    existing = load(conn, draft_id)
    if existing is None:
        raise StudioStoreError(f"no draft {draft_id} in this studio store")
    # Editing returns a submitted draft to `draft`, and this is not a convenience.
    # `submitted` means a human was asked about a specific candidate; changing the
    # candidate makes the thing they were asked about no longer the thing on the table.
    # Leaving the flag up would let an edit ride into a ceremony under a submission that
    # was made about different rules.
    conn.execute(
        "UPDATE policy_candidates SET title=?, body_json=?, updated_at=?, state=? WHERE draft_id=?",
        (
            title if title is not None else existing.title,
            _body(policies, list(effects or [])),
            to_iso(now),
            DRAFT,
            draft_id,
        ),
    )
    got = load(conn, draft_id)
    if got is None:  # pragma: no cover - the update above just wrote it
        raise StudioStoreError(f"draft {draft_id} vanished during save")
    return got


def set_state(conn: sqlite3.Connection, draft_id: str, *, state: str) -> Draft:
    """Move a draft between `draft` and `submitted`. It can move no further.

    There is deliberately no `ratified` state here. Ratification is not a property of a
    draft — it is an event in the enforcer's store with a receipt, and a flag in the
    Studio's database claiming it would be a second, unreceipted record of the one thing
    this product exists to receipt.
    """
    if state not in DRAFT_STATES:
        raise StudioStoreError(
            f"a draft's state is one of {DRAFT_STATES}, not {state!r}. There is no "
            "ratified state: ratification is a receipt in the enforcer's store, never a "
            "flag in this one."
        )
    if load(conn, draft_id) is None:
        raise StudioStoreError(f"no draft {draft_id} in this studio store")
    conn.execute("UPDATE policy_candidates SET state=? WHERE draft_id=?", (state, draft_id))
    got = load(conn, draft_id)
    if got is None:  # pragma: no cover - the update above just wrote it
        raise StudioStoreError(f"draft {draft_id} vanished during a state change")
    return got


def repin(conn: sqlite3.Connection, draft_id: str, *, base_version: str | None) -> Draft:
    """Move a draft's pin to the active version, after the operator has looked.

    Separate from `save` because re-pinning is a **decision**, not an edit. R047 §3:
    resolving a moved-beneath state invalidates every preview computed from the old
    base, and that invalidation is `canvas.build`'s job — which it can only do
    correctly if re-pinning is a distinct act it can see.
    """
    if load(conn, draft_id) is None:
        raise StudioStoreError(f"no draft {draft_id} in this studio store")
    conn.execute(
        "UPDATE policy_candidates SET base_version=? WHERE draft_id=?", (base_version, draft_id)
    )
    got = load(conn, draft_id)
    if got is None:  # pragma: no cover - the update above just wrote it
        raise StudioStoreError(f"draft {draft_id} vanished during repin")
    return got


def load(conn: sqlite3.Connection, draft_id: str) -> Draft | None:
    row = conn.execute("SELECT * FROM policy_candidates WHERE draft_id=?", (draft_id,)).fetchone()
    return None if row is None else _parse(row)


def listing(conn: sqlite3.Connection) -> list[Draft]:
    return [
        _parse(row)
        for row in conn.execute("SELECT * FROM policy_candidates ORDER BY updated_at DESC")
    ]


def delete(conn: sqlite3.Connection, draft_id: str) -> bool:
    """Discard a draft. Returns whether there was one.

    Deleting working state is ordinary; deleting evidence is impossible. That asymmetry
    is the whole reason these live in different files.
    """
    cur = conn.execute("DELETE FROM policy_candidates WHERE draft_id=?", (draft_id,))
    return cur.rowcount > 0
