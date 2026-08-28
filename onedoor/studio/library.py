"""V2 / S1 — the policy library: the version in force, read and said in English.

Two jobs, and they are separate on purpose.

**The read model** answers *what is deployed right now*, from the **snapshot behind the
pinned version** rather than from the live tables. Those are not the same question. The
tables are what the next write will change; the snapshot is what the current version
*is*, and it is the thing a receipt cites. Reading the tables would give a library page
that quietly disagrees with the digest in its own header the moment anyone writes.

**The plain-language renderer** turns one `Policy` into sentences. It is strictly
derived — every sentence comes from a field, and a field with nothing to say produces no
sentence rather than a reassuring one. *A rendering that adds a clause the policy does
not contain is a rendering that will be trusted for a guarantee nobody wrote.*

## `descriptions.py` is not this, and R055's pointer to it is a mis-citation

R055 V2 says *"plain-language rendering (descriptions.py exists for this)"*.
`studio/descriptions.py` freezes the **operator's own words** as received data — the
input to S6's proposer — and holds no renderer at all. The design note asks for
something else: *"plain-language rendering of each rule beside its YAML"*, generated
from the rule.

So both are shown, and they are labelled as different kinds of thing: what the rule
**does** (derived here, from the policy) and what someone **said it was for** (frozen
bytes, if a description exists). Reported to core rather than silently resolved, because
the two would be easy to conflate on screen and conflating them is exactly the mistake
S6's asserted/measured split exists to prevent.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import EffectPolicy, Policy, Tier
from onedoor.studio import coverage as coverage_model
from onedoor.studio import ratify

ABSENCE_IS_DENIAL = (
    "An action with no policy here is denied. This page lists what is permitted and "
    "under what limits; it is not a list of what is blocked, because nothing needs to "
    "be listed to be blocked."
)
"""The sentence R055 V2 requires on the library page.

It is the single most load-bearing fact about the engine and the easiest to get
backwards from a screen full of rules: a reader who sees six permissive-looking rows
infers a permissive system. **The default is denial, and a list of permissions read as
a list of restrictions is a misreading this page invites unless it says so.**
"""

NO_VERSION = (
    "No policy version is in force. Nothing is permitted: with no rules, every action "
    "meets the default, and the default is denial."
)
"""The empty state, which is a *state* and not an absence of one.

An empty library is not a broken page and not an open door. Saying so is the difference
between an operator who understands they have a clean install and one who assumes the
Studio failed to load.
"""

TIER_WORDS = {
    Tier.OBSERVE: "is recorded and never carried out",
    Tier.AUTO: "runs without asking",
    Tier.AUTO_CAPPED: "runs without asking, up to its caps",
    Tier.CONFIRM: "is proposed for a human to approve",
}
"""Tier as behaviour, not as a name — `AUTO_CAPPED` tells a reader nothing on its own.

Each phrase was checked against `guardrail/decision.py` rather than inferred from the
constant's spelling. `OBSERVE` in particular is the one that reads wrong from its name:
it returns `Decision.EXECUTED` and **performs nothing**, auditing a read and returning
at step 5, before bounds are even evaluated. A screen that rendered it as "observes" or
"monitors" would leave a reader guessing which.

**There is no deny tier.** Refusal is not an autonomy level in this engine — it comes
from the default-deny rule, from bounds, from caps, or from the kill switch. Inventing
a `Tier.DENY` for the table would have been a screen teaching a model of the engine
that the engine does not have.
"""


@dataclass(frozen=True)
class PolicyRow:
    """One row of the library, with everything the table shows already resolved."""

    action_type: str
    tier: Tier
    caps: str
    bounds: str
    effects: tuple[str, ...]
    coverage: str
    dry_run: bool
    is_default_deny: bool

    @property
    def state(self) -> str:
        """Which chip this row wears — the question *"what will the engine decide?"*.

        `dry_run` outranks the tier, and that ordering is the point: a rule that *would*
        permit but is running dry permits nothing, and showing it as `allowed` would be
        the screen making a promise the engine is not keeping.

        `OBSERVE` wears `allowed` even though it carries nothing out, because the chip
        answers whether the caller is refused and an observed read is not. The precision
        the chip gives up is not lost — the tier is its own column and the detail view
        says in words that nothing is performed. **Three chips over four tiers means one
        of them must be approximate; the approximation belongs where a second column
        already carries the exact answer.**
        """
        if self.is_default_deny:
            return "refuse"
        if self.dry_run or self.tier is Tier.CONFIRM:
            return "review"
        return "allow"


@dataclass(frozen=True)
class Library:
    """The whole S1 read model. Every field is resolved before rendering."""

    version: str | None
    rows: tuple[PolicyRow, ...]
    effects: tuple[EffectPolicy, ...]
    retrievable: bool
    """False when a version is in force but its snapshot cannot be read.

    The third outcome, kept apart from "no version" and from "no policies". A library
    that rendered empty for an unreadable snapshot would say *nothing is permitted*
    about a system that is permitting things right now — **the one error this page must
    never make.**
    """


def _decimal(value: object) -> str:
    """E8's shortest-exact form, so a cap reads the way the receipt spells it."""
    if value is None:
        return ""
    text = format(Decimal(str(value)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def caps_text(policy: Policy) -> str:
    parts = []
    caps = policy.caps
    if caps is not None:
        if caps.daily_rate is not None:
            parts.append(f"{caps.daily_rate}/day")
        if caps.eur_day is not None:
            parts.append(f"EUR {_decimal(caps.eur_day)}/day")
        if caps.eur_month is not None:
            parts.append(f"EUR {_decimal(caps.eur_month)}/month")
    return ", ".join(parts)


def bounds_text(policy: Policy) -> str:
    bounds = policy.bounds
    if bounds is None:
        return ""
    parts = []
    for name, span in (bounds.numeric or {}).items():
        low, high = span.min, span.max
        if low is not None and high is not None:
            parts.append(f"{name} {_decimal(low)}–{_decimal(high)}")
        elif high is not None:
            parts.append(f"{name} ≤ {_decimal(high)}")
        elif low is not None:
            parts.append(f"{name} ≥ {_decimal(low)}")
    for name, allowed in (bounds.enum or {}).items():
        parts.append(f"{name} one of {', '.join(map(str, allowed))}")
    if bounds.required:
        parts.append(f"requires {', '.join(bounds.required)}")
    if bounds.strict_params:
        parts.append("no other parameters")
    return "; ".join(parts)


def sentences(policy: Policy) -> tuple[str, ...]:
    """The rule in English. Strictly derived — no clause without a field behind it."""
    out = [f"`{policy.action_type}` {TIER_WORDS[policy.tier]}."]
    if policy.is_default_deny:
        out.append("This is the default-deny rule: it refuses anything not matched above.")
    if policy.dry_run:
        until = f" until {policy.dry_run_until}" if policy.dry_run_until else ""
        out.append(
            f"It is running **dry**{until} — the decision is made and recorded, and the "
            "action is not carried out."
        )
    if policy.requires_step_up:
        out.append("The caller must re-authenticate before this runs.")
    caps = caps_text(policy)
    if caps:
        out.append(f"Capped at {caps}, counted cumulatively across the window.")
    bounds = bounds_text(policy)
    if bounds:
        out.append(f"Parameters are bounded: {bounds}.")
    if policy.cost_param:
        out.append(f"Spend is read from the `{policy.cost_param}` parameter.")
    if policy.effects:
        out.append(f"It declares the effects {', '.join(f'`{e}`' for e in policy.effects)}.")
    if policy.compensating_command:
        window = (
            f" within {policy.undo_window_seconds} seconds"
            if policy.undo_window_seconds is not None
            else ""
        )
        out.append(f"It can be undone by `{policy.compensating_command}`{window}.")
    return tuple(out)


def _coverage_states(ledger: sqlite3.Connection, policies: list[Policy]) -> dict[str, str]:
    covered = coverage_model.build(ledger, policies=policies)
    return {row.name: row.state for row in covered.actions}


def build(ledger: sqlite3.Connection) -> Library:
    """The library as of the version in force. Reads only; writes nothing."""
    version = policy_loader.current_version(ledger)
    if version is None:
        return Library(version=None, rows=(), effects=(), retrievable=True)

    snapshot = policy_loader.snapshot_for(ledger, version)
    if snapshot is None:
        # Three outcomes: no version, a version whose snapshot is gone, and a real set.
        # This branch exists because collapsing it into "no policies" would tell an
        # operator their system permits nothing while it is permitting things.
        return Library(version=version, rows=(), effects=(), retrievable=False)

    policies = ratify._policies_at(ledger, version)
    effects = ratify._effects_at(ledger, version)
    states = _coverage_states(ledger, policies)
    rows = tuple(
        PolicyRow(
            action_type=p.action_type,
            tier=p.tier,
            caps=caps_text(p),
            bounds=bounds_text(p),
            effects=tuple(p.effects or ()),
            coverage=states.get(p.action_type, coverage_model.UNREACHED),
            dry_run=p.dry_run,
            is_default_deny=p.is_default_deny,
        )
        for p in sorted(policies, key=lambda p: p.action_type)
    )
    return Library(version=version, rows=rows, effects=tuple(effects), retrievable=True)


def policy_at(ledger: sqlite3.Connection, action_type: str) -> Policy | None:
    """One policy from the version in force, or None. Same source as `build`."""
    version = policy_loader.current_version(ledger)
    if version is None:
        return None
    for candidate in ratify._policies_at(ledger, version):
        if candidate.action_type == action_type:
            return candidate
    return None


def yaml_text(policy: Policy) -> str:
    """The rule as the operator would write it, beside the sentences.

    Emitted as JSON rather than YAML, and named for what it is. A hand-rolled YAML
    writer would be a second serializer for a format the loader already parses one way,
    and the first quoting difference between them would be a screen that shows something
    the engine would not load. **JSON is a subset of YAML**, so what is shown here is
    loadable as written — the property that actually matters.
    """
    body = {
        "action_type": policy.action_type,
        "tier": int(policy.tier),
        "dry_run": policy.dry_run,
    }
    if policy.compensating_command:
        body["compensating_command"] = policy.compensating_command
    if policy.cost_param:
        body["cost_param"] = policy.cost_param
    if policy.effects:
        body["effects"] = list(policy.effects)
    if policy.caps is not None:
        caps = {k: v for k, v in policy.caps.model_dump().items() if v is not None}
        if caps:
            body["caps"] = {k: str(v) for k, v in caps.items()}
    if policy.bounds is not None:
        bounds = _drop_nulls({k: v for k, v in policy.bounds.model_dump().items() if v})
        if bounds:
            body["bounds"] = json.loads(json.dumps(bounds, default=str))
    return json.dumps(body, indent=2, sort_keys=True)


def _drop_nulls(value: object) -> object:
    """Strip absent keys from nested structures, at every depth.

    R015: null and empty are different, and an *undeclared* bound is neither — it is
    absent. `NumericBound(max="500")` dumps as `{"max": "500", "min": null}`, and
    rendering that would show an operator a `min` they never wrote, on the page that
    exists to tell them what their rules say. **A field the policy does not declare must
    not appear on the screen that claims to show the policy.**

    Recursive rather than one level deep, because the first nested shape that needed it
    was two levels down and the second one will be three.
    """
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value]
    return value


# --- Q5: the operator's own words, kept apart from the engine's -----------------------


@dataclass(frozen=True)
class FrozenWords:
    """What an operator wrote about the proposal this rule came from.

    **Received data.** The description is frozen byte-for-byte (E10) and reaches the
    page as a quotation, attributed, never merged into the derived sentences. R058 §6:
    *the screen's value is exactly the gap between them — merging them would manufacture
    agreement.*
    """

    description_digest: str
    quotes: tuple[str, ...]
    """The phrases whose mentions name this action. Empty when the description exists
    and says nothing about this rule — which is itself worth showing, because a rule
    nobody described is a different thing from a rule with no description."""

    whole: str | None
    """The full description, or None when the bytes are not in this Studio's store."""


def frozen_words(
    enforcer: sqlite3.Connection, studio: sqlite3.Connection, action_type: str
) -> FrozenWords | None:
    """The operator's words for one rule, or None when there are none to show.

    The chain needs no stored pointer, which is why it can exist at all: a
    ratification's `candidate_digest` **is** the proposal's `policy_digest`, so the
    frozen description is reachable by recomputation from the version in force.

    Returns None rather than an empty shell when nothing links: absent is rendered by
    the caller omitting the pane, and an empty quotation would look like an operator who
    wrote nothing rather than a rule that was never proposed through the Studio.
    """
    from onedoor.studio import descriptions as descriptions_model
    from onedoor.studio import ratify as ratify_model

    latest = ratify_model.latest(enforcer)
    if latest is None:
        return None
    candidate = str(latest.get("candidate_digest") or "")
    if not candidate:
        return None
    records = descriptions_model.records_for_policy(studio, candidate)
    if not records:
        return None

    record = records[-1]
    digest = str(record.get("description_digest") or "")
    quotes = tuple(
        str(m.get("quote") or "")
        for m in record.get("mentions", [])
        if action_type in (m.get("covered_by") or []) or m.get("subject") == action_type
    )
    return FrozenWords(
        description_digest=digest,
        quotes=tuple(q for q in quotes if q),
        whole=descriptions_model.load(studio, digest) if digest else None,
    )
