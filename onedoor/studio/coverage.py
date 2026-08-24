"""The coverage map (ND-052 / S4, T1–T3).

Constitution **principle 4** — *non-coverage is stated, never silent* — as something a
deployer can look at. The three-outcome rule applied to drafting, and E11's dark surface
in product form.

Where the map's inputs come from, and why not from a description
------------------------------------------------------------------
The design note's columns start from *effects mentioned* in a description the proposer
reads — and the proposer is S6, last. So this map uses the two sources it has, and the
second is better than a description would have been:

- **the policy set** — candidate or active: what is declared;
- **the ledger** — what actually arrived, over a cited range.

*A description says what someone remembered to write down; the ledger says what
happened.* When S6 lands, the description's list joins these as a **third** source, never
replacing them.

Four states, ranked by what they do rather than by how they sound (R049 §3)
-----------------------------------------------------------------------------
| state | at decision time |
|---|---|
| `DECLARED_INERT` | a policy names an effect with **no effect policy behind it** — the label is dropped, so this is a **silent permit** |
| `UNCOVERED_OBSERVED` | the ledger saw this action type and no policy declares it — `default_deny`, a **loud denial** |
| `UNOBSERVED` | a **declared** effect nothing in the cited range exercised — *absent*, never "safe" |
| `COVERED` | declared, and every effect it names has an effect policy |

**Prominence order is `PROMINENCE`, and it is not alphabetical or alarming-sounding.**
*Uncovered* sounds bad and behaves safely: the engine refuses, loudly, and the operator
finds out. *Declared but inert* sounds fine and behaves dangerously: a silent permit
inside a rule its author believes is governing. Rank by behaviour, not by name.

What this map does not measure, stated on the map itself (R049 §4)
--------------------------------------------------------------------
`UNOBSERVED` is a row **only within a bounded vocabulary** — the effects this deployment
has declared. Action types that were never declared and never seen are an **unbounded
set**, and an unbounded set cannot be a row; that is the map's footer instead, which is
principle 4 turned on the coverage map.

And one limit found while building it: **`actions_audit` records `action_type` but not
the effects that resolved.** So effect exercise is **derived** — an effect counts as
exercised when some observed action type is declared *by the policy set being mapped* to
carry it — which is a statement about today's rules applied to yesterday's traffic, not a
record of what the engine actually resolved at the time. Rows decided under an earlier
`policy_version` may have carried different effects. The footer says so; `DERIVED_NOTE`
is that sentence, and every rendering carries it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from onedoor.guardrail import policy as policy_module
from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import EffectPolicy, Policy

COVERED = "covered"
DECLARED_INERT = "declared_inert"
UNCOVERED_OBSERVED = "uncovered_observed"
UNOBSERVED = "unobserved"

PROMINENCE = (DECLARED_INERT, UNCOVERED_OBSERVED, UNOBSERVED, COVERED)
"""Loudest first, ordered by behaviour at decision time (R049 §3).

A silent permit outranks a loud denial, which outranks a measurement nobody took, which
outranks the quiet case. Any rendering orders by this and never by name.
"""

CITED = "cited"
UNCITABLE = "uncitable"
EMPTY = "empty"
"""Three states for the range, because a store with no chain is not a store with no rows.

`CITED` — a sealed span this map can point at. `UNCITABLE` — rows exist but nothing is
chained, so the numbers are real and **cannot be cited**; that is stated, never silently
downgraded to a bare count. `EMPTY` — no decisions at all, so every observed-side
column is a non-measurement rather than a zero.
"""

DERIVED_NOTE = (
    "Effect exercise is DERIVED, not recorded: the ledger stores action types, not the "
    "effects that resolved. An effect counts as exercised when an observed action type "
    "is declared by THIS policy set to carry it — today's rules applied to past traffic. "
    "Rows decided under an earlier policy version may have carried different effects."
)

UNBOUNDED_NOTE = (
    "This map measures what is declared and what arrived over the cited range. Action "
    "types neither declared nor observed are NOT measured here: that set is unbounded, "
    "and a row cannot be drawn for something the map has never heard of."
)


@dataclass(frozen=True)
class Range:
    """The ledger span the observed-side columns were computed over."""

    state: str
    first_seq: int | None = None
    last_seq: int | None = None
    row_hash_at_last_seq: str | None = None
    rows: int = 0

    def sentence(self) -> str:
        if self.state == EMPTY:
            return "No decisions in this ledger, so nothing observed is measured."
        if self.state == UNCITABLE:
            return (
                f"{self.rows} decisions read, and this map CANNOT CITE them: the store "
                "has no hash-chained rows, so nothing here can be checked by a third "
                "party. Enable chaining and tomorrow's map is citable."
            )
        return (
            f"{self.rows} decisions read over sealed sequence {self.first_seq}–"
            f"{self.last_seq}, at row hash {self.row_hash_at_last_seq}."
        )

    def to_object(self) -> dict[str, object]:
        return {
            "state": self.state,
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
            "row_hash_at_last_seq": self.row_hash_at_last_seq,
            "rows": self.rows,
        }


@dataclass(frozen=True)
class Row:
    """One coverage finding. `detail` carries the remedy where there is one."""

    name: str
    state: str
    detail: str = ""

    def to_object(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state, "detail": self.detail}


@dataclass(frozen=True)
class CoverageMap:
    """The whole map: its citation, its rows, and what it does not measure."""

    version_hash: str | None
    cited: Range
    actions: list[Row] = field(default_factory=list)
    effects: list[Row] = field(default_factory=list)
    notes: tuple[str, ...] = (DERIVED_NOTE, UNBOUNDED_NOTE)

    def ranked(self, rows: list[Row]) -> list[Row]:
        """Loudest first, by behaviour (R049 §3), then alphabetically within a state."""
        return sorted(rows, key=lambda r: (PROMINENCE.index(r.state), r.name))

    def counts(self, rows: list[Row]) -> dict[str, int]:
        return {state: sum(1 for r in rows if r.state == state) for state in PROMINENCE}

    def citation(self) -> dict[str, object]:
        """The exportable pair a third party re-derives from (R049 §5).

        `(version_hash, range)` and nothing else — everything on this map is a pure
        function of those two, which is why the map is a **view that cites** rather than
        a receipt. `docs/coverage-derivation.md` is the other half: the derivation,
        written so a second implementation can reproduce every row.
        """
        return {
            "schema": "onedoor/coverage-citation/1",
            "version_hash": self.version_hash,
            "range": self.cited.to_object(),
        }


def _range(ledger: sqlite3.Connection) -> Range:
    total = ledger.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    if not total:
        return Range(state=EMPTY)
    tip = ledger.execute(
        "SELECT seq, row_hash FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if tip is None:
        return Range(state=UNCITABLE, rows=int(total))
    first = ledger.execute(
        "SELECT MIN(seq) AS seq FROM actions_audit WHERE seq IS NOT NULL"
    ).fetchone()
    return Range(
        state=CITED,
        first_seq=int(first["seq"]),
        last_seq=int(tip["seq"]),
        row_hash_at_last_seq=str(tip["row_hash"]),
        rows=int(total),
    )


def _observed_action_types(ledger: sqlite3.Connection) -> set[str]:
    return {
        str(row["action_type"])
        for row in ledger.execute("SELECT DISTINCT action_type FROM actions_audit")
        if row["action_type"] is not None
    }


def build(
    ledger: sqlite3.Connection,
    *,
    policies: list[Policy] | None = None,
    effects: list[EffectPolicy] | None = None,
) -> CoverageMap:
    """Map a policy set against a ledger. Reads only; writes nothing anywhere.

    `policies`/`effects` default to the set in force, so the map answers *"where are the
    gaps in what is deployed?"*. Passing a candidate answers the same question about a
    draft, which is what the canvas does.
    """
    store = policy_module.PolicyStore()
    declared = policies if policies is not None else store.all(ledger)
    if effects is not None:
        declared_effects = {e.effect for e in effects}
    else:
        declared_effects = {
            str(row["effect"]) for row in ledger.execute("SELECT effect FROM effect_policies")
        }

    observed = _observed_action_types(ledger)
    declared_actions = {p.action_type for p in declared}

    action_rows = [Row(name=action, state=COVERED) for action in declared_actions] + [
        Row(
            name=action,
            state=UNCOVERED_OBSERVED,
            detail=(
                "arrived and was refused by default-deny; no policy declares it. "
                "Declare a policy for it, or accept that it stays denied."
            ),
        )
        for action in observed - declared_actions
    ]

    # Every effect any rule names, plus every effect with a policy of its own. That union
    # is the bounded vocabulary R049 §4 allows `UNOBSERVED` to be a row within.
    named_by_rules: dict[str, list[str]] = {}
    for policy in declared:
        for effect in policy.effects:
            named_by_rules.setdefault(effect, []).append(policy.action_type)
        for rule in policy.param_effects:
            for effect in rule.add_effects:
                named_by_rules.setdefault(effect, []).append(policy.action_type)

    exercised = {
        effect for policy in declared if policy.action_type in observed for effect in policy.effects
    }

    effect_rows: list[Row] = []
    for effect in sorted(set(named_by_rules) | declared_effects):
        rules = sorted(set(named_by_rules.get(effect, [])))
        if effect not in declared_effects:
            effect_rows.append(
                Row(
                    name=effect,
                    state=DECLARED_INERT,
                    detail=(
                        f"labelled by {', '.join(rules)} but no effect policy declares it, "
                        "so the label is dropped at decision time: no tier floor, no effect "
                        "caps. Declare the effect policy, or remove the label."
                    ),
                )
            )
        elif effect not in exercised:
            effect_rows.append(
                Row(
                    name=effect,
                    state=UNOBSERVED,
                    detail=(
                        "declared, and nothing in the cited range exercised it. Absent, "
                        "not safe: this is a measurement nobody took, not a clean result."
                    ),
                )
            )
        else:
            effect_rows.append(Row(name=effect, state=COVERED))

    return CoverageMap(
        version_hash=policy_loader.current_version(ledger) if policies is None else None,
        cited=_range(ledger),
        actions=action_rows,
        effects=effect_rows,
    )
