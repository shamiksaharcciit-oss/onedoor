"""Collect a candidate's validation problems instead of raising at the first (S3-T1).

`policy_loader.validate_policy` is fail-closed: it raises `ValueError` on the first
thing it finds. That is right for boot — a process that starts on a half-valid policy
set is a process making decisions under rules nobody approved — and wrong for a canvas,
because an editor that dies on an invalid draft is not an editor.

**This is a wrapper over that function, never a second validator.** Fence post two
(R046 §3) says every number the canvas shows is produced by an engine function; the same
applies to every *judgement*. A canvas with its own idea of what makes a policy invalid
is a second implementation of a rule that has an owner, and the two will disagree in the
direction that lets a bad rule through — the Studio saying "looks fine" and the loader
refusing at boot.

The honesty clause, which is the part that matters
----------------------------------------------------
This reports **problems found**, never *all problems*, and it says so in those words
wherever it is rendered. Two reasons, both structural rather than incidental:

1. `validate_policy` **stops at its first failure per rule**, so a policy with two
   defects reports one, and the second appears only after the first is fixed.
2. Set-level defects are **invisible to a per-rule loop**. A `compensating_command`
   naming an action the candidate does not define, an effect floor that only bites once
   two rules are read together — nothing here can see them, because nothing here looks
   at more than one rule at a time.

A list presented as complete would be exactly the overclaim this programme exists to
make impossible. An empty list means *nothing was found*, which is a weaker and truer
statement than *nothing is wrong*.
"""

from __future__ import annotations

from dataclasses import dataclass

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import EffectPolicy, Policy

FOUND_WORDING = "problems found"
"""The exact words, referenced by the renderer and by the tests that hold them.

One constant rather than two strings that happen to agree — R045 §1's law applied to
prose, the same way `NO_BACKTEST_SENTENCE` holds S2's absence statement.
"""

INCOMPLETE_NOTICE = (
    "These are the problems found, not all problems: the engine's validator stops at "
    "the first failure in each rule, and defects that only appear when rules are read "
    "together are invisible to a per-rule check."
)
"""Rendered wherever a problem list is shown, including when the list is empty."""


@dataclass(frozen=True)
class Problem:
    """One thing the engine's own validator refused, attributed to the rule it came from."""

    action_type: str
    message: str

    def to_object(self) -> dict[str, str]:
        return {"action_type": self.action_type, "message": self.message}


def problems(candidate: list[Policy], effects: list[EffectPolicy] | None = None) -> list[Problem]:
    """Every problem `validate_policy` raises, one rule at a time, collected.

    The engine keeps raising; the Studio gets a list. Ordered by action type so the same
    draft produces the same list twice — an editor whose error list reshuffles between
    renders is an editor nobody trusts.

    `effects` is accepted and deliberately not separately checked: effect policies have
    no `validate_policy` of their own because the engine validates them **in the model**,
    at construction. Adding a hand-written check for them here would be precisely the
    second validator this module exists not to be. They are still part of the candidate
    the caller passes on, so the parameter stays rather than making callers remember
    which half of a candidate this function wanted.
    """
    _ = effects
    found: list[Problem] = []
    for policy in sorted(candidate, key=lambda p: p.action_type):
        try:
            policy_loader.validate_policy(policy)
        except ValueError as exc:
            found.append(Problem(action_type=policy.action_type, message=str(exc)))
    return found


def summary(found: list[Problem]) -> str:
    """One line, and it never claims completeness — see the module note.

    Phrased as a count after the constant rather than around it, so the singular case
    does not need a second wording. Two spellings of one sentence are two names for one
    fact, and R045 §1 ruled on what happens to those.
    """
    return f"{FOUND_WORDING}: {len(found)}"
