"""V5 / S3 — drafts: the pipeline the engine already has, made visible.

A **read model over `canvas.build`**, plus the shape of the ratification ceremony. It
computes nothing the engine does not already compute: `canvas` builds the panels,
`validate` finds the problems, `backtest` replays, `ratify` performs the swap. This
module decides only what a reader is shown and in what order.

## The ceremony's gravity comes from what is true

R060 §5, and it is the constraint that shapes every sentence below. The weight of the
ratify page must come from **the digest, the diff, and the irreversibility stated** —
never from an element that dramatizes beyond what the engine does. *A ceremony that
overstates is a design-study banner away from a lie.*

So the page says three things and no more than three: what will be in force after,
what changes, and what this does not undo. Concretely, the two claims it does **not**
make:

- It does not say the change is reversible. There is no un-ratify; the remedy is
  ratifying again, which is a new receipt and a new version, and the page says that
  rather than offering comfort the engine cannot back.
- It does not say the backtest predicts the future. `backtest` replays *recorded*
  decisions under candidate rules; a divergence count is a statement about the past,
  and the panel is worded as one.

## Fence post one, restated

Nothing in this module writes to the enforcer store. Ratification goes through
`server.ratify_draft` → `ratify.ratify`, which is the ceremony, sealed on arrival.
`drafts.py` prepares what the operator sees before they confirm and renders what came
back after; it never applies anything itself.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Policy
from onedoor.studio import canvas as canvas_model
from onedoor.studio import store as store_model
from onedoor.studio import validate

IRREVERSIBLE = (
    "Ratifying applies these rules to the enforcer store and seals a receipt. There is "
    "no un-ratify: to go back you ratify again, which is a new version and a new "
    "receipt. Nothing that already happened under the old rules is changed by either."
)
"""What the confirm actually commits to, in the words the engine can back.

Not "this cannot be undone" — that would be false, and falsely frightening. The truth
is narrower and more useful: **the way back is forward**, and the record keeps both.
"""

BACKTEST_IS_ABOUT_THE_PAST = (
    "A backtest replays decisions this ledger already recorded against the candidate "
    "rules. It says what would have happened, not what will."
)
"""The panel's own limit, stated on the panel. A divergence count read as a forecast is
the overclaim this screen is most likely to invite."""

STALE_BASE = (
    "This draft was written against a version that is no longer in force. Every number "
    "on this page was computed from that base, so none of them is shown. Re-pin to "
    "recompute them together."
)

FLIP_WORDS = {
    ("denied", "allowed"): "permits what was refused",
    ("denied", "to_approval"): "sends for approval what was refused",
    ("allowed", "denied"): "refuses what was permitted",
    ("allowed", "to_approval"): "sends for approval what ran without asking",
    ("to_approval", "allowed"): "runs without asking what needed approval",
    ("to_approval", "denied"): "refuses what was sent for approval",
}
"""The mockup's sentence pattern, one per direction.

Each says what the *change* does, in the tense of a decision that already happened —
because that is what a replay is about. A single "N verdicts changed" would hide the
one direction an operator must never miss: **`permits what was refused`.**
"""

WIDENING = frozenset({("denied", "allowed"), ("denied", "to_approval"), ("to_approval", "allowed")})
"""Directions that let through more than before.

Called out separately because the count alone treats a loosening and a tightening as
the same event, and they are not the same event.
"""


def flip_sentence(key: str) -> tuple[str, bool]:
    """`"denied->allowed"` → (sentence, is_widening).

    An unknown pair returns its own raw form rather than a guess: a direction this
    module has no sentence for is a direction it must not paraphrase.
    """
    was, _, now = key.partition("->")
    pair = (was, now)
    return FLIP_WORDS.get(pair, f"{was} became {now}"), pair in WIDENING


@dataclass(frozen=True)
class RuleDiff:
    """One rule's was / would-become, as the reader sees it."""

    action_type: str
    kind: str
    """`added` or `modified` — `ratify.Changes` has no `removed`, by R046's ruling."""

    was: Policy | None
    becomes: Policy | None


@dataclass(frozen=True)
class DraftView:
    """Everything S3 shows about one draft, resolved before rendering."""

    draft: store_model.Draft
    view: canvas_model.CanvasView
    diffs: tuple[RuleDiff, ...]

    @property
    def stale(self) -> bool:
        """The pin moved, so every computed number on this page is about a dead base."""
        return self.view.panels is None

    @property
    def problems(self) -> list[validate.Problem]:
        return list(self.view.problems)


def _by_action(policies: list[Policy]) -> dict[str, Policy]:
    return {p.action_type: p for p in policies}


def diffs_for(view: canvas_model.CanvasView, was: list[Policy]) -> tuple[RuleDiff, ...]:
    """Per-rule was / would-become, from the preview the ceremony itself computed.

    The `added`/`modified` split comes from `ratify.diff`, so the page and the receipt
    cannot disagree about what changed — the same reason the coverage map cites its
    inputs rather than recomputing them.
    """
    panels = view.panels
    if panels is None:
        return ()
    previous = _by_action(was)
    candidate = _by_action(view.draft.policies)
    out = []
    for kind, names in (
        ("added", panels.preview.changes.added),
        ("modified", panels.preview.changes.modified),
    ):
        for name in names:
            out.append(
                RuleDiff(
                    action_type=name,
                    kind=kind,
                    was=previous.get(name),
                    becomes=candidate.get(name),
                )
            )
    return tuple(sorted(out, key=lambda d: (d.kind, d.action_type)))


def build(
    enforcer: sqlite3.Connection,
    studio: sqlite3.Connection,
    draft_id: str,
    *,
    config: EngineConfig,
    with_backtest: bool = False,
) -> DraftView:
    """One draft, ready to render."""
    view = canvas_model.build(
        enforcer, studio, draft_id, config=config, with_backtest=with_backtest
    )
    was: list[Policy] = []
    if view.panels is not None:
        from onedoor.studio import ratify as ratify_model

        was = ratify_model._policies_at(enforcer, view.panels.preview.from_version)
    return DraftView(draft=view.draft, view=view, diffs=diffs_for(view, was))


def listing(studio: sqlite3.Connection) -> list[store_model.Draft]:
    return store_model.listing(studio)
