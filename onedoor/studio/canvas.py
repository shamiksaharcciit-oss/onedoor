"""The canvas's view model (ND-052 / S3, T3 and T4).

Everything the canvas shows, assembled here so the renderer computes nothing. Same
split that keeps `viewer/page.py` from growing a second opinion about whether a receipt
is sound, and the same reason: two implementations of a fact eventually disagree, and
the one the user sees is the one that is wrong.

**Every number here is produced by an engine function** (fence post two, R046 §3): the
previewed hash by `ratify.preview`, the diff by `ratify.diff`, divergence and coverage
by S1's `backtest.run`, the problem list by `validate.problems` wrapping the engine's
own validator. Nothing in this module computes a summary of its own.

Pin and surface, and what it costs the panels (R047 §3)
--------------------------------------------------------
A draft is pinned to the version it was opened against. When the active set moves, the
canvas does **not** silently re-base: a live re-base is S2's stale read arriving one
layer earlier, before anyone clicks, where the compare-and-swap cannot catch it. The
moved state is surfaced instead, and it **names both hashes** — *a warning that names
no versions is a mood, not a fact.*

The consequence R047 attached is the reason `Panels` is one object rather than three
fields: **every number goes stale together and recomputes together.** A diff from base
X beside a preview from base Y is two truths about different worlds on one screen. So
the panels are computed as a unit or not at all, and a stale draft has `panels is None`
— there is no code path that can produce one panel from a base the diff no longer uses,
because there is no code path that produces one panel at all.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.studio import backtest, ratify, store, validate

CURRENT = "current"
MOVED = "moved"
"""The two states of a draft's pin, and the second one names both hashes.

There is no third: a draft opened on a store with no recorded version pins `None`, and
`None` compares against the active version exactly like any other value — absent moving
to present is a move, and it is described as one.
"""

BACKTEST_NOT_REQUESTED = "not_requested"
BACKTEST_REFUSED = "refused"
BACKTEST_RAN = "ran"
"""Three outcomes for the divergence panel, and none of them is an empty table.

*Not requested* is a choice the caller made. *Refused* is the engine declining to
receipt an unciteable range (R043 §2) and it carries the refusal's own words. Only
*ran* has numbers. A canvas that rendered all three as "0 divergences" would be
reporting a measurement it never took.
"""


@dataclass(frozen=True)
class Pin:
    """Where the draft is pinned, and whether the world has moved under it."""

    state: str
    base_version: str | None
    active_version: str | None

    @property
    def has_moved(self) -> bool:
        return self.state == MOVED

    def sentence(self) -> str:
        """Names both hashes, because a warning that names none is a mood, not a fact."""
        if self.state == CURRENT:
            return "This draft is pinned to the policy version currently in force."
        return (
            f"The rules moved beneath this draft, from {_name(self.base_version)} to "
            f"{_name(self.active_version)}. Nothing shown was computed against the "
            "version now in force."
        )

    def to_object(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "base_version": self.base_version,
            "active_version": self.active_version,
        }


def _name(version: str | None) -> str:
    """Absent renders as words. A blank where a hash goes reads as a missing value."""
    return "no recorded version" if version is None else version


@dataclass(frozen=True)
class Divergence:
    """What the candidate would have done to the ledger, or why there is no answer."""

    state: str
    receipt: backtest.BacktestReceipt | None = None
    refusal: str | None = None

    def to_object(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "receipt": None if self.receipt is None else self.receipt.sealed(),
            "refusal": self.refusal,
        }


@dataclass(frozen=True)
class Panels:
    """Every computed number, produced from ONE base and carried as one object.

    One object rather than three fields, deliberately: *two fields that must agree are
    a bug waiting* (X-14), and three panels that must all describe the same base are
    three chances to show a number from a world the diff has left.
    """

    computed_from: str | None
    preview: ratify.Preview
    divergence: Divergence

    def to_object(self) -> dict[str, Any]:
        return {
            "computed_from": self.computed_from,
            "to_version": self.preview.to_version,
            "changes": self.preview.changes.to_object(),
            "effect_changes": self.preview.effect_changes.to_object(),
            "candidate_digest": self.preview.candidate_digest,
            "divergence": self.divergence.to_object(),
        }


@dataclass(frozen=True)
class CanvasView:
    """The whole screen. The renderer reads this and computes nothing."""

    draft: store.Draft
    pin: Pin
    problems: list[validate.Problem]
    problems_summary: str
    panels: Panels | None

    @property
    def is_stale(self) -> bool:
        """True exactly when the panels are absent — one condition, not two."""
        return self.panels is None


def pin_of(draft: store.Draft, active_version: str | None) -> Pin:
    state = CURRENT if draft.base_version == active_version else MOVED
    return Pin(state=state, base_version=draft.base_version, active_version=active_version)


def build(
    enforcer: sqlite3.Connection,
    studio: sqlite3.Connection,
    draft_id: str,
    *,
    config: EngineConfig,
    with_backtest: bool = False,
    ledger_provenance: str = backtest.LIVE,
) -> CanvasView:
    """Assemble the canvas for one draft. Reads the enforcer's store; writes nothing to it.

    Fence post one (R046 §3): the canvas edits candidates and touches nothing else. The
    enforcer connection is opened for reading — `ratify.preview` does its work in a
    scratch database and `backtest.run` in another, so neither adds a row here nor moves
    a cap counter.
    """
    draft = store.load(studio, draft_id)
    if draft is None:
        raise store.StudioStoreError(f"no draft {draft_id} in this studio store")

    pin = pin_of(draft, policy_loader.current_version(enforcer))
    found = validate.problems(draft.policies, draft.effects)

    panels = None
    if not pin.has_moved:
        panels = _panels(
            enforcer,
            draft,
            config=config,
            with_backtest=with_backtest,
            ledger_provenance=ledger_provenance,
        )
    return CanvasView(
        draft=draft,
        pin=pin,
        problems=found,
        problems_summary=validate.summary(found),
        panels=panels,
    )


def _panels(
    enforcer: sqlite3.Connection,
    draft: store.Draft,
    *,
    config: EngineConfig,
    with_backtest: bool,
    ledger_provenance: str,
) -> Panels:
    preview = ratify.preview(enforcer, draft.policies, effects=draft.effects)
    return Panels(
        computed_from=draft.base_version,
        preview=preview,
        divergence=_divergence(
            enforcer,
            draft,
            config=config,
            with_backtest=with_backtest,
            ledger_provenance=ledger_provenance,
        ),
    )


def _divergence(
    enforcer: sqlite3.Connection,
    draft: store.Draft,
    *,
    config: EngineConfig,
    with_backtest: bool,
    ledger_provenance: str,
) -> Divergence:
    if not with_backtest:
        return Divergence(state=BACKTEST_NOT_REQUESTED)
    try:
        receipt = backtest.run(
            enforcer,
            draft.policies,
            config=config,
            provenance=ledger_provenance,
            effects=draft.effects,
        )
    except backtest.BacktestRefused as exc:
        # The refusal's own words, not a paraphrase. `backtest.run` refuses an
        # unchained store because a citation-free receipt would be the store vouching
        # for itself, and that reasoning is worth more on screen than "no data".
        return Divergence(state=BACKTEST_REFUSED, refusal=str(exc))
    return Divergence(state=BACKTEST_RAN, receipt=receipt)


def open_draft_from_active(
    enforcer: sqlite3.Connection,
    studio: sqlite3.Connection,
    *,
    title: str,
    now: Any,
    draft_id: str | None = None,
) -> store.Draft:
    """Start a draft as a COPY of the rules in force, pinned to their version.

    The natural first move is "load what is live and change one rule", and a copy keeps
    fence post one intact: the canvas reads the active policies and writes only to its
    own store. Nothing here is a reference to the enforcer's rows — a later edit to the
    draft cannot reach them, because there is nothing to reach through.
    """
    from onedoor.guardrail import policy as policy_module

    reader = policy_module.PolicyStore()
    effects = [
        effect
        for effect in (
            reader.get_effect(enforcer, row["effect"])
            for row in enforcer.execute("SELECT effect FROM effect_policies ORDER BY effect")
        )
        if effect is not None
    ]
    return store.create(
        studio,
        title=title,
        policies=reader.all(enforcer),
        effects=effects,
        base_version=policy_loader.current_version(enforcer),
        now=now,
        draft_id=draft_id,
    )
