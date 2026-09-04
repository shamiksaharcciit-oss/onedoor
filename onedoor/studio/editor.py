"""V7 / S2 — the editor: a guided form and the raw rule, always in sync.

Two panes over **one rule at a time**, inside a draft, and never anywhere near the live
policy set.

## How "always in sync" is achieved, and why not the obvious way

The obvious way is JavaScript: parse the raw pane in the browser, mirror it into the
form, and mirror the form back. **That requires a second implementation of the policy
parser**, in a different language, and the two would disagree on exactly the inputs this
engine cares about most — decimal strings, unicode, key order, `null` against absent.
R062 §1 named the law for the replay and it applies unchanged here: *two implementations
of a thing disagree the first time anything subtle changes.*

So the panes sync through the **server**, which owns the only parser. Editing either
pane and submitting re-renders **both** from one parsed model. They cannot drift,
because there is nothing to drift *between*: what you see in each pane is one object,
rendered twice.

The cost is a round trip per edit. The benefit is that the raw pane always shows
something the engine would actually load, and the form never shows a value the raw pane
would parse differently.

## Fence post one

Everything here edits `store.Draft` rows in the **Studio's** database.
`policy_loader.upsert` is never called, the enforcer connection is never written, and
the only path from a draft to the live rules remains the ratification ceremony. R047 §2
stands: *the enforcer's database contains no row the Studio can edit.*
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from onedoor.guardrail.models import Bounds, Caps, NumericBound, Policy, Tier

DECIMAL_DIVERGENCE = (
    "Decimal strings are accepted here and are what the draft stores. Be aware of how "
    "the engine treats them today: a cap reads a decimal string exactly, and a numeric "
    "bound over the same parameter refuses it. Declaring a numeric bound on a parameter "
    "therefore changes which wire types that action accepts."
)
"""The ND-054 note, at the decimal fields (R055 V7, R062 §5).

**It describes what the engine does today, and nothing else.** No "will be fixed", no
"until ND-054 lands", no softening toward a change that has not happened: *a note that
describes tomorrow's behaviour is aspiration dressed as capability, one field at a time.*

The wording is drawn from `TICKETS-ND-054.md` §3, which measured it on shipped code —
`caps.resolve_cost` accepts `str`, `bounds` does not.
"""

DECIMAL_FIELDS = ("caps.eur_day", "caps.eur_month", "bounds.numeric")
"""Where the note is shown. Named rather than guessed at render time, so a field added
without a note is a visible omission rather than a silent one."""

NOT_IN_THE_FORM = (
    "param_effects",
    "dry_run_until",
    "is_default_deny",
)
"""Policy fields the guided form does not offer, and the raw pane does.

Declared rather than left implicit: the form is a **subset** by design, and a reader
must be able to find out which subset without diffing two renderings. Editing these
means editing the raw pane, which is why the raw pane is not a convenience.
"""


class EditError(ValueError):
    """The submitted rule could not be understood. Carries what to tell the operator."""


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    value: str
    kind: str = "text"
    options: tuple[tuple[str, str], ...] = ()
    note: str = ""


def _decimal_or_none(raw: str, field: str) -> Decimal | None:
    """The operator's text as an exact `Decimal`. **Never routed through `float`.**

    E8: `Decimal(text)` is exact, so `"0.1"` is a tenth and not the binary approximation
    of one. Parsing to `float` to "check" the input would reintroduce at the check the
    hazard the decimal form exists to avoid — which is the shape of the defect `ND-054`
    was raised about, met from the other side.

    A `Decimal` is returned rather than the string because that is what the models
    declare; pydantic would coerce either way, and passing the type the field asks for
    means the coercion is not doing work nobody can see.
    """
    text = raw.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise EditError(f"{field}: {text!r} is not a decimal number") from None


def _int_or_none(raw: str, field: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise EditError(f"{field}: {text!r} is not a whole number") from None


def _numeric_clauses(name: str, span: dict[str, object]) -> list[str]:
    """One clause per bound present, both when both are — R089 F-E1.

    The ternary this replaced printed `max` OR `min`, never both: on a rule with both
    bounds (`payments.transfer`'s `amount_eur`, min 0.01 max 2000), the guided pane read
    **"amount_eur max 2000"** with the min silently gone, beside a raw pane that kept
    both, beneath a caption claiming *"both panes are rendered from the same parsed rule,
    so they cannot disagree."* They disagreed, in saved state, reproducibly.

    Two clauses for one name round-trip through `_numeric_from` correctly — its parser
    already merges same-named clauses (`existing.min`/`existing.max` carried across),
    which is why the fix is which strings this function emits, not a parser change.
    """
    clauses = []
    if span.get("max") is not None:
        clauses.append(f"{name} max {span['max']}")
    if span.get("min") is not None:
        clauses.append(f"{name} min {span['min']}")
    return clauses


def fields_for(policy: Policy) -> tuple[Field, ...]:
    """The guided pane, rendered from the same *dumped* values the raw pane shows.

    `model_dump()` and not the attributes, and the difference is not cosmetic: the model
    holds `Decimal("500.00")` and dumps the E8 canonical `"500"`. Reading attributes here
    put `500.00` in the form beside `500` in the raw pane — **the two panes disagreeing,
    which is the one thing this design claims is impossible.** Caught by
    `test_both_panes_are_rendered_from_one_object`, which is what that test is for.

    One object, one canonicalisation, rendered twice.
    """
    dumped = policy.model_dump()
    caps_dump = dumped.get("caps") or {}
    bounds_dump = dumped.get("bounds") or {}
    bounds = policy.bounds
    numeric = ", ".join(
        clause
        for name, span in (bounds_dump.get("numeric") or {}).items()
        for clause in _numeric_clauses(name, span)
    )
    return (
        Field("action_type", "Action type", policy.action_type),
        Field(
            "tier",
            "Tier",
            str(int(policy.tier)),
            kind="select",
            options=tuple((str(int(t)), f"{t.name} ({int(t)})") for t in Tier),
        ),
        Field("dry_run", "Dry run", "1" if policy.dry_run else "", kind="checkbox"),
        Field(
            "compensating_command",
            "Compensating command",
            policy.compensating_command or "",
        ),
        Field("cost_param", "Cost parameter", policy.cost_param or ""),
        Field(
            "caps.eur_day",
            "Cap, EUR per day",
            "" if caps_dump.get("eur_day") is None else str(caps_dump["eur_day"]),
            note=DECIMAL_DIVERGENCE,
        ),
        Field(
            "caps.eur_month",
            "Cap, EUR per month",
            "" if caps_dump.get("eur_month") is None else str(caps_dump["eur_month"]),
            note=DECIMAL_DIVERGENCE,
        ),
        Field(
            "caps.daily_rate",
            "Cap, actions per day",
            "" if caps_dump.get("daily_rate") is None else str(caps_dump["daily_rate"]),
        ),
        Field(
            "bounds.required",
            "Required parameters",
            ", ".join(bounds.required or ()) if bounds else "",
        ),
        Field(
            "bounds.numeric",
            "Numeric bounds",
            numeric,
            note=DECIMAL_DIVERGENCE,
        ),
        Field(
            "bounds.strict_params",
            "No other parameters",
            "1" if bounds and bounds.strict_params else "",
            kind="checkbox",
        ),
    )


def raw_for(policy: Policy) -> str:
    """The raw pane: the rule as JSON, which is loadable YAML.

    Same reasoning as the library's rule pane — a hand-rolled YAML writer would be a
    second serializer for a format the loader already parses one way.
    """
    body: dict[str, object] = {
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
        caps = {k: str(v) for k, v in policy.caps.model_dump().items() if v is not None}
        if caps:
            body["caps"] = caps
    if policy.bounds is not None:
        bounds: dict[str, object] = {}
        if policy.bounds.numeric:
            bounds["numeric"] = {
                name: {k: str(v) for k, v in span.model_dump().items() if v is not None}
                for name, span in policy.bounds.numeric.items()
            }
        if policy.bounds.enum:
            bounds["enum"] = {k: list(v) for k, v in policy.bounds.enum.items()}
        if policy.bounds.required:
            bounds["required"] = list(policy.bounds.required)
        if policy.bounds.strict_params:
            bounds["strict_params"] = True
        if bounds:
            body["bounds"] = bounds
    return json.dumps(body, indent=2, sort_keys=True)


def _numeric_from(text: str) -> dict[str, NumericBound]:
    """`amount_eur max 500, n min 1` → bounds. Deliberately narrow and strict.

    A permissive parser here would guess, and a guess about a bound is a guess about
    what the engine will refuse.
    """
    out: dict[str, NumericBound] = {}
    for clause in (c.strip() for c in text.split(",")):
        if not clause:
            continue
        parts = clause.split()
        if len(parts) != 3 or parts[1] not in ("min", "max"):
            raise EditError(
                f"numeric bounds: {clause!r} is not understood. Write "
                "`amount_eur max 500` or `amount_eur min 1`, separated by commas."
            )
        name, which, raw = parts
        value = _decimal_or_none(raw, f"numeric bound on {name}")
        existing = out.get(name, NumericBound())
        out[name] = NumericBound(
            min=value if which == "min" else existing.min,
            max=value if which == "max" else existing.max,
        )
    return out


def policy_from_form(fields: dict[str, list[str]], *, base: Policy) -> Policy:
    """Build a rule from the guided pane, keeping fields the form does not offer.

    `base` matters: the form is a subset (`NOT_IN_THE_FORM`), and rebuilding from the
    form alone would silently drop whatever it does not show. **A partial editor that
    writes a whole object deletes what it never displayed.**
    """

    def one(name: str, default: str = "") -> str:
        return (fields.get(name) or [default])[0]

    caps = Caps(
        daily_rate=_int_or_none(one("caps.daily_rate"), "cap, actions per day"),
        eur_day=_decimal_or_none(one("caps.eur_day"), "cap, EUR per day"),
        eur_month=_decimal_or_none(one("caps.eur_month"), "cap, EUR per month"),
    )
    required = [p.strip() for p in one("bounds.required").split(",") if p.strip()]
    bounds = Bounds(
        numeric=_numeric_from(one("bounds.numeric")),
        enum=base.bounds.enum if base.bounds else {},
        required=required,
        strict_params=bool(one("bounds.strict_params")),
    )
    tier_raw = one("tier", str(int(base.tier)))
    try:
        tier = Tier(int(tier_raw))
    except (ValueError, TypeError):
        raise EditError(f"tier: {tier_raw!r} is not one of {[t.name for t in Tier]}") from None

    return base.model_copy(
        update={
            "action_type": one("action_type", base.action_type).strip() or base.action_type,
            "tier": tier,
            "dry_run": bool(one("dry_run")),
            "compensating_command": one("compensating_command").strip(),
            "cost_param": one("cost_param").strip() or None,
            "caps": caps,
            "bounds": bounds,
        }
    )


def policy_from_raw(text: str, *, base: Policy) -> Policy:
    """Build a rule from the raw pane. One parser, and it is this one."""
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EditError(f"the rule is not valid JSON: {exc.msg} at line {exc.lineno}") from None
    if not isinstance(body, dict):
        raise EditError("the rule must be an object, not a list or a bare value")
    # Merge into the base's own dump and validate ONCE, rather than validating the
    # fragment and copying it over. `model_copy(update=...)` does not re-validate, so a
    # nested model arrives as a plain dict and the object looks like a Policy while
    # behaving like a mapping -- the failure surfaces three screens later, in a renderer.
    # Merging first also preserves the fields the raw pane omitted (`NOT_IN_THE_FORM`).
    merged = {**base.model_dump(), **body}
    try:
        return Policy.model_validate(merged)
    except Exception as exc:
        raise EditError(f"the rule is not a valid policy: {exc}") from None
