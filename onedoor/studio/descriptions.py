"""Frozen descriptions and derivation records (ND-052 / S6, T2–T3).

**A description is RECEIVED DATA (E10).** It is the operator's own words, and it is the
input to a derivation that gets a record — so it is frozen **byte-for-byte as received**
and never normalised. No whitespace stripping, no Unicode normalisation, no line-ending
translation, no formatter anywhere near this path.

That is not fastidiousness. The description's SHA-256 is what the derivation record cites,
so any byte that changes between *what the operator wrote* and *what was hashed* silently
breaks the tie between the record and its input. A description CRLF-translated by git on a
Windows checkout would change the instrument's input with nothing visible changing — which
is why it is stored as a **BLOB** and why any committed fixture description needs a
`.gitattributes` `-text` fence with the rationale written into the file.

Why here and not in the enforcer's store
------------------------------------------
R047 §2's line still holds: **the enforcer's database contains no row the Studio can
edit.** Descriptions and derivation records are the proposer's working evidence, and they
live in `studio.db` with the drafts. What crosses into the enforcer's store is the
ratification — through the ceremony, sealed on arrival — and nothing else.

Lineage needs no new field, exactly as it needed none for the pack: a ratification's
`candidate_digest` **is** the proposal's `policy_digest` by construction, so a derivation
record is matched to the receipt it led to by **recomputation** rather than by a stored
pointer.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from typing import Any

from onedoor.store.clock import to_iso
from onedoor.studio.proposer import DerivationRecord

SCHEMA_SQL = """
-- E10: RECEIVED DATA. `body` is a BLOB and holds the operator's bytes verbatim -- not
-- TEXT, because a TEXT column invites a decode/encode round trip and this value must
-- survive one that never happens.
CREATE TABLE IF NOT EXISTS descriptions (
    description_digest TEXT PRIMARY KEY,
    body               BLOB NOT NULL,
    created_at         TEXT NOT NULL
);

-- Derivation records. NOT receipts: a proposal is not recomputable, and principle 5 was
-- amended rather than stretched to say so (R053 section 1). Append-only, because a record
-- of what a model produced that the producer can quietly revise is not a record.
CREATE TABLE IF NOT EXISTS derivation_records (
    record_digest       TEXT PRIMARY KEY,
    description_digest  TEXT NOT NULL,
    policy_digest       TEXT NOT NULL,
    proposer_provenance TEXT NOT NULL,
    body_json           TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS derivation_records_no_update
BEFORE UPDATE ON derivation_records
BEGIN SELECT RAISE(ABORT, 'derivation_records is append-only'); END;

CREATE TRIGGER IF NOT EXISTS derivation_records_no_delete
BEFORE DELETE ON derivation_records
BEGIN SELECT RAISE(ABORT, 'derivation_records is append-only'); END;
"""


def freeze(conn: sqlite3.Connection, description: str, *, now: datetime) -> str:
    """Store a description verbatim and return its digest.

    Idempotent by content: the same bytes hash to the same digest and insert once, so
    re-proposing from an unchanged description does not multiply rows.
    """
    raw = description.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    conn.execute(
        "INSERT INTO descriptions (description_digest, body, created_at) VALUES (?,?,?) "
        "ON CONFLICT(description_digest) DO NOTHING",
        (digest, raw, to_iso(now)),
    )
    return digest


def load(conn: sqlite3.Connection, description_digest: str) -> str | None:
    """The description, decoded only at the boundary where a caller needs to read it.

    Stored and hashed as bytes; decoded here and nowhere else. `errors="strict"` on
    purpose — a description that does not decode is a **failure to surface**, never a
    silently repaired string, because a repaired string would no longer hash to the digest
    the record cites and the mismatch would look like tampering.
    """
    row = conn.execute(
        "SELECT body FROM descriptions WHERE description_digest=?", (description_digest,)
    ).fetchone()
    if row is None:
        return None
    return bytes(row["body"]).decode("utf-8")


def raw(conn: sqlite3.Connection, description_digest: str) -> bytes | None:
    """The stored bytes, undecoded — what the digest was actually taken over."""
    row = conn.execute(
        "SELECT body FROM descriptions WHERE description_digest=?", (description_digest,)
    ).fetchone()
    return None if row is None else bytes(row["body"])


def store_record(conn: sqlite3.Connection, record: DerivationRecord, *, now: datetime) -> str:
    sealed = record.sealed()
    conn.execute(
        "INSERT INTO derivation_records (record_digest, description_digest, policy_digest, "
        "proposer_provenance, body_json, created_at) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(record_digest) DO NOTHING",
        (
            sealed["record_digest"],
            record.description_digest,
            record.policy_digest,
            record.proposer_provenance,
            json.dumps(sealed, sort_keys=True, separators=(",", ":")),
            to_iso(now),
        ),
    )
    return str(sealed["record_digest"])


def load_record(conn: sqlite3.Connection, record_digest: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT body_json FROM derivation_records WHERE record_digest=?", (record_digest,)
    ).fetchone()
    return None if row is None else dict(json.loads(row["body_json"]))


def records_for_policy(conn: sqlite3.Connection, policy_digest: str) -> list[dict[str, Any]]:
    """Every derivation that produced this candidate — the lineage, by recomputation.

    A ratification's `candidate_digest` **is** a proposal's `policy_digest`, so asking
    *"where did the policy I ratified come from?"* is this query and needs no stored
    pointer between the two stores.
    """
    return [
        dict(json.loads(row["body_json"]))
        for row in conn.execute(
            "SELECT body_json FROM derivation_records WHERE policy_digest=? "
            "ORDER BY created_at, record_digest",
            (policy_digest,),
        )
    ]
