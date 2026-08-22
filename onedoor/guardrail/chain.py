"""Turning the chain on, and walking it afterwards (ND-001 / C3, C4).

Two things live here because they are two halves of one fact: **where the chain
starts**. `enable()` writes that boundary down; `verify_chain()` reads it back and
refuses to pretend either side of it is the other.

Why the chain cannot simply be retro-fitted
-------------------------------------------
`actions_audit` has an `actions_audit_no_update` trigger. Existing rows cannot be
given a hash, ever, by design — the table that would need editing is the one whose
whole value is that it cannot be edited. So the chain begins at a **genesis** row
carrying `prev_hash` = 64 ASCII zeros (R016's ruled sentinel: an affirmative in-band
statement that no predecessor exists, which leaves NULL exactly one meaning), and
every row before it stays unchained forever.

That is not a defect to apologise for. It is a boundary, and the honest thing is to
record where it falls and report it — which is what makes a mixed archive readable
rather than suspicious.

Four outcomes, and R031 §2 asked for them by name
-------------------------------------------------
*"a broken link, an absent chain, and an unverifiable row are three verdicts, not
one"* — plus `verified`. A log with an unchained prefix and an intact chain after
genesis is **not** "verified" and **not** "failed". It is both, stated per region, and
a verifier that averaged them into one word would be the two-outcome collapse this
programme keeps catching.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from onedoor.guardrail.audit import CHAIN_ENABLED_KEY  # noqa: E402  (one constant, one home)
from onedoor.guardrail.preimage import GENESIS_PREV_HASH, row_hash_of
from onedoor.guardrail.receipt import Status
from onedoor.store.clock import now_utc, to_iso

CHAIN_GENESIS_KEY = "chain.genesis_after_id"
"""The id of the last row written BEFORE chaining was switched on.

Recorded so a walker can say which prefix is unchained **from the store** rather than
inferring it from where the NULLs happen to stop. An inference would be right until
the day it was not — a restored backup, a partial copy — and it would be wrong
silently.
"""


class ChainError(RuntimeError):
    """Enabling the chain was refused. Never raised by verification."""


@dataclass(frozen=True)
class Region:
    """One contiguous stretch of the ledger and what can be said about it."""

    status: Status
    first_id: int
    last_id: int
    rows: int
    detail: str


@dataclass(frozen=True)
class ChainReport:
    """The walk's whole answer, region by region.

    Deliberately not a boolean and not a single status. The question "is this log
    intact?" has more than one true answer at once whenever a chain was switched on
    partway through a system's life, which is every real deployment.
    """

    regions: tuple[Region, ...]

    @property
    def broken(self) -> tuple[Region, ...]:
        return tuple(r for r in self.regions if r.status in (Status.FAILED, Status.UNVERIFIABLE))

    @property
    def chained_rows(self) -> int:
        return sum(r.rows for r in self.regions if r.status is Status.VERIFIED)

    @property
    def unchained_rows(self) -> int:
        return sum(r.rows for r in self.regions if r.status is Status.ABSENT)

    @property
    def sound(self) -> bool:
        """True when nothing is broken. An unchained prefix does not make it False.

        A store that predates `ND-001` is not a compromised store, and reporting it as
        one would train an operator to ignore the alarm.
        """
        return not self.broken


def enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM config WHERE key=?", (CHAIN_ENABLED_KEY,)).fetchone()
    return row is not None and row["value"] == "1"


def genesis_after_id(conn: sqlite3.Connection) -> int | None:
    """The last unchained row's id, or None when chaining was never enabled."""
    row = conn.execute("SELECT value FROM config WHERE key=?", (CHAIN_GENESIS_KEY,)).fetchone()
    return None if row is None else int(row["value"])


def enable(conn: sqlite3.Connection) -> int:
    """Switch chaining on, once, recording where the boundary falls.

    Must be called inside a transaction by the caller. Returns the id of the last
    unchained row (0 on a fresh store).

    Refuses a second call rather than starting a second chain. Two genesis points in
    one ledger would mean two answers to "where does the chain begin", and a walker
    reaching the second one could not tell a fresh start from a break — which is
    precisely the shape of damage a chain exists to detect.
    """
    if enabled(conn):
        raise ChainError(
            "chaining is already enabled for this store; a second genesis would make "
            "a break and a fresh start indistinguishable"
        )
    row = conn.execute("SELECT MAX(id) AS last FROM actions_audit").fetchone()
    boundary = int(row["last"] or 0)
    stamp = to_iso(now_utc())
    for key, value in ((CHAIN_ENABLED_KEY, "1"), (CHAIN_GENESIS_KEY, str(boundary))):
        conn.execute(
            "INSERT INTO config (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, stamp),
        )
    return boundary


def verify_chain(conn: sqlite3.Connection) -> ChainReport:
    """Walk the ledger and report each region honestly.

    Never re-queries anything but the store, never repairs, never raises on damage:
    damage is a verdict, not an exception. A verifier that threw on a broken chain
    would be a verifier nobody could run against a suspect archive, which is the only
    archive worth running one against.
    """
    rows = list(
        conn.execute(
            "SELECT id, seq, prev_hash, row_hash FROM actions_audit ORDER BY id"
        ).fetchall()
    )
    if not rows:
        return ChainReport(regions=())

    boundary = genesis_after_id(conn)
    regions: list[Region] = []

    unchained = [r for r in rows if r["seq"] is None and r["row_hash"] is None]
    if unchained:
        detail = (
            "written before the chain was switched on; these rows cannot be hashed "
            "retroactively because the table forbids UPDATE"
            if boundary is not None
            else "chain not yet in operation (ND-001)"
        )
        regions.append(
            Region(
                status=Status.ABSENT,
                first_id=int(unchained[0]["id"]),
                last_id=int(unchained[-1]["id"]),
                rows=len(unchained),
                detail=detail,
            )
        )

    partial = [
        r
        for r in rows
        if (r["seq"] is None) != (r["row_hash"] is None)
        or (r["seq"] is not None) != (r["prev_hash"] is not None)
    ]
    if partial:
        regions.append(
            Region(
                status=Status.UNVERIFIABLE,
                first_id=int(partial[0]["id"]),
                last_id=int(partial[-1]["id"]),
                rows=len(partial),
                detail=(
                    "chain columns are partly written: this is a chain that ran and "
                    "did not finish, which is a different fact from one that never ran"
                ),
            )
        )

    chained = [r for r in rows if r["seq"] is not None and r["row_hash"] is not None]
    if not chained:
        return ChainReport(regions=tuple(regions))

    regions.extend(_walk(conn, chained))
    return ChainReport(regions=tuple(regions))


def _walk(conn: sqlite3.Connection, chained: list[sqlite3.Row]) -> list[Region]:
    """Check every chained row's digest and link, localising any break to its row."""
    expected_prev = GENESIS_PREV_HASH
    expected_seq = 1
    ok_from: int | None = None
    ok_count = 0
    regions: list[Region] = []

    def close_ok(last_id: int) -> None:
        nonlocal ok_from, ok_count
        if ok_from is not None:
            regions.append(
                Region(
                    status=Status.VERIFIED,
                    first_id=ok_from,
                    last_id=last_id,
                    rows=ok_count,
                    detail="every row hashes to its successor's prev_hash",
                )
            )
            ok_from, ok_count = None, 0

    for row in chained:
        full = conn.execute("SELECT * FROM actions_audit WHERE id=?", (row["id"],)).fetchone()
        problems = []
        if int(row["seq"]) != expected_seq:
            problems.append(f"seq is {row['seq']}, expected {expected_seq}")
        if str(row["prev_hash"]) != expected_prev:
            problems.append("prev_hash does not name the previous row's hash")
        recomputed = row_hash_of(full)
        if recomputed != str(row["row_hash"]):
            problems.append("the row's contents do not hash to its recorded row_hash")

        if problems:
            close_ok(int(row["id"]) - 1)
            regions.append(
                Region(
                    status=Status.FAILED,
                    first_id=int(row["id"]),
                    last_id=int(row["id"]),
                    rows=1,
                    detail="; ".join(problems),
                )
            )
        else:
            if ok_from is None:
                ok_from = int(row["id"])
            ok_count += 1

        # Continue from what the STORE says rather than from what was expected, so a
        # single tampered row is reported once instead of poisoning every row after
        # it. Localising the break is the whole point of the DoD's tamper test.
        expected_prev = str(row["row_hash"])
        expected_seq = int(row["seq"]) + 1

    close_ok(int(chained[-1]["id"]))
    return regions
