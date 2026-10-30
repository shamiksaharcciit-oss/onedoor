"""V3 / S4 — the execution ledger, read and never written.

The decisions the engine actually made, as a filterable register. **Read-only, with no
mutating path in the module at all** — *"no mutation of any kind on this
screen"* is the requirement, and the way that is kept is that nothing here can write: every query is a
`SELECT`, and the connection is the same read path the library uses.

## Entries are numbered by the chain, not by the page

`seq` is the hash-chain sequence number the row was sealed with — the same number
`prev_hash`/`row_hash` link. Numbering rows by their position in a filtered listing
would invent an ordinal that changes when a filter changes, and an auditor quoting
"entry 14" would be quoting the page rather than the ledger. **A register's numbers
belong to the register.**

Rows that predate the chain carry no `seq`, and those render as absent rather than as
zero — see `Entry.number`.

## The filter this page does not offer

The filters expected here are *"time, action, verdict, policy version, key"*. Four of those
are columns. **The fifth is recorded, but not as something to filter by.**
`onedoor.service` authenticates `/v1/decide` callers with bearer API keys and, since
migration `0029`, records who asked: `decide_principal`, a keyed fingerprint of the
bearer key (`onedoor.service.app.State.principal`), never the key itself. It answers
*who*, but a fingerprint is not a value a reader can type into a filter and recognize —
this page does not offer one on it, a gap stated rather than quietly left unmentioned.

`source` is a different column and must not be offered in its place: it means
*how the request was built* (scheduler, rule, llm, ui), documented in the model as
**"informational only, never affects the decision"** — so offering it as an actor
filter would answer a question about identity with a fact about provenance.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

MISSING_ACTOR_FILTER = (
    "Filtering by API key is not offered. The decision service does record who asked "
    "(a keyed fingerprint of the bearer key, never the key itself) on every decision "
    "made through /v1/decide, but a fingerprint is not something a reader can type "
    "into a filter and recognize, so this page does not offer one on it."
)
"""Stated on the page. An absent capability that is silently omitted reads as a
capability that exists and found nothing."""

DECISION_STATE = {
    "executed": "allow",
    "dry_run": "review",
    "proposed": "review",
    "denied": "refuse",
    "failed": "refuse",
}
"""Which chip a verdict wears. `failed` is `refuse`-coloured and **is not a refusal** —
the detail view says which it was, and the word on the chip is the decision's own word,
never a colour standing in for it."""

PAGE_SIZE = 50


@dataclass(frozen=True)
class Entry:
    """One decision, as the register shows it."""

    row_id: int
    seq: int | None
    created_at: str
    action_type: str
    decision: str
    reason_code: str
    policy_version: str | None
    source: str
    outcome: str | None
    row_hash: str | None

    @property
    def number(self) -> str:
        """The chain's sequence number, or a stated absence.

        Rows written before the hash chain existed have no `seq`. Rendering `0` or a
        page-relative index would give an auditor a number the ledger never assigned.
        """
        return f"#{self.seq}" if self.seq is not None else "unchained"

    @property
    def state(self) -> str:
        return DECISION_STATE.get(self.decision, "review")


@dataclass(frozen=True)
class Filters:
    """What the reader asked for. Every field is exactly what came off the query
    string, so the page can echo back what it filtered on rather than what it meant."""

    action: str = ""
    verdict: str = ""
    version: str = ""
    source: str = ""
    since: str = ""
    until: str = ""

    def active(self) -> dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass(frozen=True)
class Page:
    entries: tuple[Entry, ...] = ()
    total: int = 0
    filters: Filters = field(default_factory=Filters)
    truncated: bool = False
    """True when more rows match than this page shows.

    Named rather than left implicit: *no silent caps.* A register that quietly shows the
    first fifty of nine hundred reads as a register with fifty entries.
    """


def _where(filters: Filters) -> tuple[str, list[Any]]:
    """Build the WHERE clause. Parameterised throughout — a filter value is a reader's
    input and reaches SQL only as a bound parameter, never as text."""
    clauses, params = ["kind = 'decision'"], []
    for column, value in (
        ("action_type", filters.action),
        ("decision", filters.verdict),
        ("policy_version", filters.version),
        ("source", filters.source),
    ):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if filters.since:
        clauses.append("created_at >= ?")
        params.append(filters.since)
    if filters.until:
        clauses.append("created_at <= ?")
        params.append(filters.until)
    return " AND ".join(clauses), params


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        row_id=int(row["id"]),
        seq=None if row["seq"] is None else int(row["seq"]),
        created_at=str(row["created_at"] or ""),
        action_type=str(row["action_type"] or ""),
        decision=str(row["decision"] or ""),
        reason_code=str(row["reason_code"] or ""),
        policy_version=row["policy_version"],
        source=str(row["source"] or ""),
        outcome=row["outcome"],
        row_hash=row["row_hash"],
    )


def page(ledger: sqlite3.Connection, filters: Filters | None = None) -> Page:
    """One page of the register, newest first."""
    filters = filters or Filters()
    where, params = _where(filters)
    total = int(
        ledger.execute(f"SELECT COUNT(*) AS n FROM actions_audit WHERE {where}", params).fetchone()[
            "n"
        ]
    )
    rows = ledger.execute(
        f"SELECT * FROM actions_audit WHERE {where} ORDER BY id DESC LIMIT ?",
        [*params, PAGE_SIZE],
    ).fetchall()
    return Page(
        entries=tuple(_entry(r) for r in rows),
        total=total,
        filters=filters,
        truncated=total > len(rows),
    )


def choices(ledger: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    """The values actually present, so a filter cannot offer a choice that finds nothing.

    Read from the ledger rather than from the enum, deliberately: a verdict the engine
    can produce but this store has never held is not a useful filter, and offering it
    teaches a reader that the empty result means something it does not.
    """
    out = {}
    for name, column in (
        ("action", "action_type"),
        ("verdict", "decision"),
        ("version", "policy_version"),
        ("source", "source"),
    ):
        rows = ledger.execute(
            f"SELECT DISTINCT {column} AS v FROM actions_audit "
            f"WHERE kind='decision' AND {column} IS NOT NULL AND {column} != '' "
            f"ORDER BY {column}"
        ).fetchall()
        out[name] = tuple(str(r["v"]) for r in rows)
    return out


def entry(ledger: sqlite3.Connection, row_id: int) -> sqlite3.Row | None:
    """The whole row for the detail view. One `SELECT`, no interpretation here."""
    row: sqlite3.Row | None = ledger.execute(
        "SELECT * FROM actions_audit WHERE id = ? AND kind = 'decision'", (row_id,)
    ).fetchone()
    return row


#: The digest columns, with what each one actually covers. Labels checked against
#: `guardrail/digests.py` rather than guessed from the letter: E/I/T/V are evidence,
#: instrument, trust and verdict, and a screen that captioned `t_digest` as "target"
#: because a neighbouring tool uses T that way would be confidently wrong in a compliance product.
DIGEST_LABELS = (
    ("e_digest", "Evidence", "what was asked: the request as the decision saw it"),
    ("i_digest", "Instrument", "the policy and configuration that decided"),
    ("t_digest", "Trust", "what a verifier must accept to close the check"),
    ("v_digest", "Verdict", "the decision itself"),
)

CHAIN_LABELS = (
    ("seq", "Sequence"),
    ("prev_hash", "Previous row"),
    ("row_hash", "This row"),
    ("anchor_ref", "Anchor"),
)
