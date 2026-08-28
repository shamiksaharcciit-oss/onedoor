"""V6 / the flagship — *"was this correct under last week's rules?"*, in one click.

One recorded decision, replayed against the policy set of any version this store can
retrieve, with the original verdict beside it.

## The premise, verified rather than assumed

R055 V6 says to check first whether ratified policy sets are retrievable by version.
They are: `policy_loader.record_snapshot` writes the whole set into `policy_versions`
keyed by its hash, `snapshot_for` returns it, and `ratify._policies_at` rebuilds
`Policy` objects from it. V4 leaned on the same path for its budget limits and a test
proved it by writing a divergent cap into the live table and watching the bar hold
still. No escalation was needed.

**But retrievable is not the same as always retrievable**, which is why
`NOT_RETRIEVABLE` exists. A version can be named by an audit row and have no snapshot —
a store restored from a partial backup, a row written before snapshots, a hash from
another deployment. That renders as *not retrievable*, **never as absent and never as an
empty policy set**: an empty set would replay as default-deny and produce a confident
`denied` that means nothing. R055 V6's own words: *three-outcome honesty applies to our
own feature.*

## The engine decides, not this module

The replay builds a **scratch database in a temporary directory**, loads the historical
policies into it, and calls `decide_and_reserve` — the same entry point the live service
calls. `backtest.run` established the pattern and the reason: *the instrument is
identical, not merely the answer plausible.* A hand-written comparison of rules would be
a second implementation of the verdict, and the two would disagree the first time
anything subtle changed.

Nothing here touches the enforcer store. The scratch database is deleted when the
temporary directory closes.

## What the screen must say (R061 §5)

**Both versions in the same breath** — the one that decided then, the one replaying now
— and the *would-have* limit sentence the backtest panel carries. A counterfactual that
does not name its counterfactual-ness on the screen where it renders is the backtest
panel's lie one click deeper.
"""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Policy
from onedoor.store.db import Database, tx
from onedoor.studio import backtest, ratify

WOULD_HAVE = (
    "This replays one recorded decision against a different version's rules. It says "
    "what would have been decided, not what will be. Nothing was re-executed and "
    "nothing in the ledger changed."
)
"""R061 §5, and the same limit the backtest panel wears.

Two clauses, and both are load-bearing. *Would have, not will* keeps the counterfactual
from reading as a prediction. *Nothing was re-executed* keeps it from reading as an
action — this page runs a decision function, and an operator who thinks a payment was
attempted twice has been badly misled by a button.
"""

NOT_RETRIEVABLE = "not retrievable"
"""A version this store cannot rebuild. **Never rendered as an empty policy set.**

An empty set replays as default-deny and returns a confident `denied` that means
nothing — the most dangerous possible answer, because it is the shape of a real verdict.
"""

UNREPLAYABLE = "cannot be replayed"
"""The row itself cannot be rebuilt into a request — absent or malformed `params_json`.

Distinct from *not retrievable*, which is about the rules. One is a fact about the
question, the other about the yardstick, and they have different remedies.
"""


@dataclass(frozen=True)
class Verdict:
    """One side of the comparison."""

    version: str | None
    decision: str
    tier: int | None

    @property
    def shape(self) -> str:
        return backtest._shape(self.decision)


@dataclass(frozen=True)
class Comparison:
    """Then and now, and whether they differ.

    `now` is None when the replay could not be performed; `reason` says which of the
    two failures it was. **A comparison that could not be made is not a comparison that
    found no difference**, and the type keeps those apart rather than the caller
    remembering to.
    """

    then: Verdict
    now: Verdict | None
    against: str
    """The version the replay was run against — named on screen beside `then.version`."""

    reason: str | None = None

    @property
    def changed(self) -> bool | None:
        """True, False, or **None when it could not be evaluated**."""
        if self.now is None:
            return None
        return self.then.shape != self.now.shape


def retrievable_versions(ledger: sqlite3.Connection) -> tuple[str, ...]:
    """Every version this store can actually rebuild a policy set for.

    Read from `policy_versions` rather than from the audit log's distinct
    `policy_version` values, and the difference is the whole point: the dropdown must
    offer what `snapshot_for` **can serve**, not what some row once named. R056 ruled
    the screen copy for exactly this — *the version dropdown lists what `snapshot_for`
    can honestly serve; anything it cannot serve renders "not retrievable", never as
    absent.*
    """
    rows = ledger.execute(
        "SELECT version_hash FROM policy_versions ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    return tuple(str(r["version_hash"]) for r in rows)


def _policies_at(ledger: sqlite3.Connection, version: str) -> list[Policy] | None:
    if policy_loader.snapshot_for(ledger, version) is None:
        return None
    return ratify._policies_at(ledger, version)


def compare(
    ledger: sqlite3.Connection,
    row: sqlite3.Row,
    against: str,
    *,
    config: EngineConfig,
) -> Comparison:
    """Replay `row` under the policy set of `against`, beside what was decided then.

    Read-only with respect to every store the caller owns: the replay happens in a
    throwaway database that exists for the duration of this call.
    """
    then = Verdict(
        version=row["policy_version"],
        decision=str(row["decision"] or ""),
        tier=None if row["effective_tier"] is None else int(row["effective_tier"]),
    )

    policies = _policies_at(ledger, against)
    if policies is None:
        return Comparison(then=then, now=None, against=against, reason=NOT_RETRIEVABLE)

    request = backtest._request_from(row)
    if request is None:
        return Comparison(then=then, now=None, against=against, reason=UNREPLAYABLE)

    effects = ratify._effects_at(ledger, against)
    with tempfile.TemporaryDirectory(prefix="onedoor-reevaluate-") as scratch:
        database = Database(str(Path(scratch) / "at-version.db"))
        database.init()
        conn = database.connect()
        try:
            with tx(conn):
                for effect in effects:
                    policy_loader.upsert_effect(conn, effect)
            for policy in policies:
                policy_loader.upsert(conn, policy)
            outcome = decide_and_reserve(request, conn=conn, config=config, now=request.created_at)
        finally:
            conn.close()

    if isinstance(outcome, PermittedIntent):
        now = Verdict(version=against, decision="executed", tier=int(outcome.effective_tier))
    else:
        now = Verdict(
            version=against,
            decision=outcome.decision.decision.value,
            tier=int(outcome.decision.effective_tier),
        )
    return Comparison(then=then, now=now, against=against)
