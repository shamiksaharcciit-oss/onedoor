"""Guardrail data models and enums — the contract every other module depends on.

Pure data: no I/O, no DB. Requests are frozen; only persisted approval rows carry
mutable lifecycle state.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from onedoor._vendor.canonical import canon_decimal

# A constrained recursive JSON value — keeps params typed under mypy --strict and
# makes the (untrusted) params surface explicit.
#
# `Decimal` is here because E10 rules that JSON numbers are parsed with
# `parse_float=Decimal`: nothing on the evaluation path may become an IEEE double, so
# a number that arrives over the wire arrives as a Decimal and must be representable
# in the envelope that records it. `float` remains accepted for the in-process
# binding, whose callers hand Python objects directly rather than bytes; a float
# param now compares exactly against a Decimal bound, which is strictly better than
# the float-versus-float comparison it replaces. Whether the in-process boundary
# should refuse floats outright is a live question with core, not assumed here.
type JsonValue = (
    str | int | float | Decimal | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class Tier(IntEnum):
    """Autonomy tier per action type. IntEnum so the kill switch can clamp via min()."""

    OBSERVE = 0
    AUTO = 1
    AUTO_CAPPED = 2
    CONFIRM = 3


class Source(StrEnum):
    """Who built the request. Informational only — never affects the decision."""

    SCHEDULER = "scheduler"
    RULE = "rule"
    LLM = "llm"
    UI = "ui"
    UNDO = "undo"
    SYSTEM = "system"


class Decision(StrEnum):
    EXECUTED = "executed"
    DRY_RUN = "dry_run"
    PROPOSED = "proposed"
    DENIED = "denied"
    FAILED = "failed"


class Outcome(StrEnum):
    """What the enforcement point reports actually happened (ND-039, AADP A4b).

    A SEPARATE vocabulary from :class:`Decision`. `Decision` is the PDP's verdict --
    what was authorized; `Outcome` is the PEP's report -- what occurred. Overloading
    one with the other is how they got conflated in the first place: `report_result`
    took `ok: bool`, so `not_attempted` and `timeout` both collapsed into `failed`,
    the audit asserted an attempt that never happened, and the reservation settled
    before anything looked at the outcome -- **permanently charging budget for an
    action that never occurred**. That was a live conformance defect against `-00`,
    disclosed against `<=0.3.6`.

    Disposition, ruled by R005 and enforced in `report_result`:

        success        -> SETTLE   the action happened
        failure        -> SETTLE   it was attempted and did not succeed
        timeout        -> SETTLE   it may have happened; assume it did
        not_attempted  -> RELEASE  a positive assertion that it did not happen

    **Settle on doubt.** Release requires a positive assertion of non-occurrence,
    never an absence of information -- a timeout is doubt, not evidence. And the
    release is an AUDITED event, symmetric with reclamation expiry, never a silent
    adjustment: the audit's job is to make a false report attributable, not to
    prevent a trusted reporter from lying.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    NOT_ATTEMPTED = "not_attempted"


class CheckId(StrEnum):
    """Which check produced the decision — recorded for full explainability."""

    KILL_SWITCH = "kill_switch"
    DEFAULT_DENY = "default_deny"
    BOUNDS = "bounds"
    # aadp/0.2 (ND-002, E1). Unit-neutral: the window and the unit belong in the
    # `budget` object (ND-003), not in the reason code. cap_daily_rate -> cap_rate;
    # cap_eur_day AND cap_eur_month both -> cap_value, which is why ND-003's
    # budget_json is not optional -- without it the evidence store can no longer
    # tell a day-cap breach from a month-cap one, a granularity regression on 0.3.5.
    #
    # Clean break, no dual emission. Safe because reason codes are AUDIT vocabulary:
    # a PEP's behaviour is fixed by the verdict, never by the reason string, so a
    # -00 PEP that has never heard of cap_value still denies correctly. The
    # deprecated codes are retained permanently in the IANA registry and MUST NOT be
    # emitted by a PDP advertising aadp/0.2+.
    CAP_RATE = "cap_rate"
    CAP_VALUE = "cap_value"
    DRY_RUN = "dry_run"
    TIER_CONFIRM = "tier_confirm"
    NO_COMPENSATION = "no_compensating_command"
    OBSERVE = "observe"
    PASSED = "passed"
    EFFECT_FLOOR = "effect_floor"
    MALFORMED = "malformed"
    COST_UNKNOWN = "cost_unknown"
    EXPIRED = "expired"  # a permit's reservation was reclaimed past its deadline
    # RESERVED, NEVER EMITTED until ND-005 wires the sender-binding check (E5). The
    # code lands now so the vocabulary change is complete in ONE breaking increment;
    # emitting it before the check exists would be a reason code for a check that
    # never ran. tests/guardrail/test_reason_vocabulary.py holds it unemitted.
    SENDER_MISMATCH = "sender_mismatch"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTED = "executed"


class NumericBound(BaseModel):
    """An inclusive numeric range for a parameter.

    `Decimal`, not `float`. These bounds are compared against parameter values that
    arrive over the wire, and E10 forbids an IEEE double anywhere on the evaluation
    path: a float bound admits any value that rounds onto it, so a request could
    exceed the policy maximum by up to half an ulp and be allowed (S2, disclosed
    against <=0.3.6). Pydantic coerces int/float/str literals in policy YAML to
    Decimal here, so a policy written `max: 500.10` gets exactly 500.10.
    """

    model_config = ConfigDict(extra="forbid")
    min: Decimal | None = None
    max: Decimal | None = None

    @field_serializer("min", "max")
    def _canonical(self, value: Decimal | None) -> str | None:
        """Serialize through the canonical renderer, never `str(Decimal)`.

        `bounds_json` is part of the policy snapshot, and the snapshot is hashed into
        `version_hash`. Pydantic's default for Decimal is `str()`, which preserves
        authored scale -- so `max: 100.00` and `max: 100` would hash differently while
        meaning the same rule (E8's named trap, S3 in the policy hash). One form, or
        the content-hash stops meaning "the rules changed".
        """
        return None if value is None else canon_decimal(value)


class Bounds(BaseModel):
    """Parameter bounds for an action type. Lives in the policy table (invariant 6)."""

    model_config = ConfigDict(extra="forbid")
    numeric: dict[str, NumericBound] = Field(default_factory=dict)
    enum: dict[str, list[str]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    strict_params: bool = True  # reject unknown params (injection defense)


class Caps(BaseModel):
    """Per-action-type caps. €/day and €/month apply to Tier 2 only."""

    model_config = ConfigDict(extra="forbid")
    daily_rate: int | None = None
    eur_day: Decimal | None = None
    eur_month: Decimal | None = None

    @field_serializer("eur_day", "eur_month")
    def _canonical(self, value: Decimal | None) -> str | None:
        """Same reason as `NumericBound`: `caps_json` is hashed into the policy version."""
        return None if value is None else canon_decimal(value)


class OpaqueHosts(BaseModel):
    """Hosts whose real target cannot be determined without a network call (U4).

    A shortener canonicalizes perfectly -- the host really is `t.co` -- so no amount
    of canonicalization catches it. Following the redirect is a network call, which
    the PDP's offline evaluation model forbids. What is left is to **declare** that a
    host is opaque, and treat a member as *possibly the declared target*, because it
    might be.

    **Absent means the mechanism is off.** A rule that does not carry an `opaque`
    block behaves exactly as it did without this feature -- the same opt-in discipline
    as `url` itself.
    """

    model_config = ConfigDict(extra="forbid")
    builtin: bool = True
    """Use the shipped, versioned starter list (`onedoor/opaque-hosts/1`)."""
    extra: list[str] = Field(default_factory=list)
    """The deployer's own redirectors. A starter list is not a census, and an
    environment's internal link-wrapper is known to its operator, not to us."""


class UrlMatch(BaseModel):
    """URL-typed matching for a parameter (ND-040 / U2). **Opt-in.**

    A regex over a URL's *string* form is the wrong parser for a URL: it is defeated
    by percent-encoding, a `user@host` prefix, a trailing dot, case, an IP literal and
    IDN homographs. This form matches the **canonicalized** target instead, so
    `bank%2Eexample%2Ecom` and `BANK.Example.COM.` reach the same rule that
    `bank.example.com` does.

    Declaring this is a deliberate act. A rule that does not carry a `url` block keeps
    its regex semantics **exactly**, byte for byte -- no deployed policy changes
    meaning because the engine was upgraded. Opt-in, never silent reinterpretation.
    """

    model_config = ConfigDict(extra="forbid")
    hosts: list[str] = Field(default_factory=list)
    """Declared hosts. Canonicalized on both sides before comparison."""
    include_subdomains: bool = False
    """Explicit rather than implied: the two readings disagree exactly where an
    attacker lives, and suffix matching without a label boundary is the classic
    bypass (`bank.example.com.evil.test`)."""
    cidrs: list[str] = Field(default_factory=list)
    """Networks matched when the target is an IP literal -- the case a hostname
    pattern cannot express at all."""
    schemes: list[str] = Field(default_factory=list)
    """Optional restriction. Empty means any scheme."""
    opaque: OpaqueHosts | None = None
    """Declared opaque hosts (U4). A member is treated as though it were a declared
    host, because the engine cannot rule out that it is one. Absent means off: nothing
    that is not a declared member is ever touched, which is how `innocent-ok` stays
    3/3 while the shortener stops passing."""


class ParamEffectRule(BaseModel):
    """Deterministic rule: a parameter value adds effects when it matches.

    For generic tools (http, shell) whose real-world effect depends on their
    arguments: `param` names the parameter, `add_effects` are the labels gained on
    match, and the match itself is either

    * `pattern` -- a full-match regex against the value's string form, the original
      form, unchanged in meaning; or
    * `url` -- URL-typed matching against the canonicalized target (`ND-040`).

    Exactly one, so a rule cannot silently mean two things.
    """

    model_config = ConfigDict(extra="forbid")
    param: str
    pattern: str | None = None
    url: UrlMatch | None = None
    add_effects: list[str]

    @model_validator(mode="after")
    def _exactly_one_matcher(self) -> ParamEffectRule:
        if (self.pattern is None) == (self.url is None):
            raise ValueError(
                f"param_effects rule for {self.param!r} must declare exactly one of "
                f"`pattern` or `url` -- a rule that declares both has two meanings, "
                f"and one that declares neither has none"
            )
        return self


class EffectPolicy(BaseModel):
    """Effect-level governance shared by every action carrying the label."""

    model_config = ConfigDict(extra="forbid")
    effect: str
    min_tier: Tier | None = None
    caps: Caps = Field(default_factory=Caps)


class Policy(BaseModel):
    """One row of the policy table."""

    model_config = ConfigDict(extra="forbid")
    action_type: str
    tier: Tier
    bounds: Bounds = Field(default_factory=Bounds)
    caps: Caps = Field(default_factory=Caps)
    effects: list[str] = Field(default_factory=list)
    param_effects: list[ParamEffectRule] = Field(default_factory=list)
    dry_run: bool = True
    dry_run_until: datetime | None = None
    compensating_command: str | None = None
    # Which parameter carries the money. A euro cap is a statement about an
    # amount, and the engine has no way to know which parameter holds it. If a
    # euro cap applies and this is unset, the request must declare `cost_eur`
    # itself -- and if neither is available the decision is a denial, never an
    # assumed zero. An unknown amount that silently passes a budget check is
    # the whole defect.
    cost_param: str | None = None
    undo_window_seconds: int = 900
    requires_step_up: bool = False
    is_default_deny: bool = False


def _reject_non_json(value: object, path: str = "params") -> None:
    """Refuse types that are not JSON values even though Pydantic would coerce them.

    ``bytes`` is decoded to ``str`` and ``set``/``tuple`` are converted to ``list``
    by lax validation, which means the decision point would validate and audit a
    *different object* from the one the enforcement point holds. The evidence
    record must describe what will actually be acted on.
    """
    if isinstance(value, str | int | float | Decimal | bool | None.__class__):
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _reject_non_json(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, item in value.items():
            if not isinstance(k, str):
                raise ValueError(f"{path}: non-string key {k!r}")
            _reject_non_json(item, f"{path}.{k}")
        return
    raise ValueError(f"{path}: {type(value).__name__} is not a JSON value")


class ActionRequest(BaseModel):
    """The universal envelope every source produces. Frozen once built."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID
    action_type: str
    params: dict[str, JsonValue] = Field(default_factory=dict)
    source: Source
    rationale: str
    session_id: str | None = None
    cost_eur: Decimal = Decimal(0)
    created_at: datetime
    parent_audit_id: int | None = None
    params_raw: str | None = None
    """The verbatim source text of `params` as the enforcement point sent it (E10).

    Set only by ingress paths that actually receive bytes -- the HTTP service and the
    MCP proxy. The in-process binding is handed objects and leaves this None, which
    is what makes the two cases distinguishable in the evidence row rather than
    guessed at. Never derived from `params`: a value reconstructed here would be a
    PDP serialization wearing the label "received"."""

    @field_validator("params", mode="before")
    @classmethod
    def _params_are_json(cls, v: object) -> object:
        _reject_non_json(v)
        return v


class Budget(BaseModel):
    """Machine-readable budget state on a cap denial (ND-003, AADP A4).

    Present **iff** the verdict is `deny` and the reason is `cap_value` or
    `cap_rate`. It exists because `aadp/0.2` made the reason codes unit-neutral:
    `cap_value` collapses what used to be `cap_eur_day` and `cap_eur_month`, so
    without this object the evidence store can no longer tell a day-cap breach from
    a month-cap one -- a granularity regression against 0.3.5, where the reason code
    alone carried it. Confirmed normative under the evidence section (E7): a
    `cap_value` denial that cannot name its window is not re-derivable.

    Persisted to `budget_json`, not merely returned. All seven fields are REQUIRED.
    Currency lives in `unit`, never in a field name -- that is what "unit-neutral"
    means, and it is what lets tokens or call counts use the same shape later
    (ND-027) without another vocabulary change.

    Numerics are decimal STRINGS in canonical shortest-exact form, never floats and
    never JSON numbers: one form for wire, storage and preimage (E8).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    dimension: Literal["value", "rate"]
    unit: str
    """ISO 4217 for a value dimension ("EUR"); a token for a rate ("calls")."""
    window: str
    """"day" | "month" | an ISO-8601 duration."""
    limit: str
    consumed: str
    remaining: str
    window_resets_at: str
    """RFC3339, UTC, canonical -- the instant the window rolls and the budget frees."""


class PolicyDecision(BaseModel):
    """The fully-explainable verdict."""

    model_config = ConfigDict(extra="forbid")
    decision: Decision
    effective_tier: Tier
    nominal_tier: Tier
    reason_code: CheckId
    detail: str = ""
    dry_run: bool = False
    requires_approval: bool = False
    compensating_command: str | None = None
    budget: Budget | None = None
    """Set iff `decision` is a denial and `reason_code` is `cap_value`/`cap_rate`."""


class ActionResult(BaseModel):
    """What evaluation produced."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    decision: PolicyDecision
    executed: bool | None = False
    """True on success, False on a failed/timed-out attempt, **None when the action
    was never attempted** (ND-039). None is not False: recording False would assert
    an attempt that did not happen, which is the first half of the A4b defect."""
    connector_ok: bool | None = None
    connector_payload: dict[str, JsonValue] | None = None
    error: str | None = None
    audit_id: int | None = None
    approval_id: int | None = None
    undo_available_until: datetime | None = None


class Approval(BaseModel):
    """Persisted Tier-3 approval with mutable lifecycle state."""

    model_config = ConfigDict(extra="forbid")
    approval_id: int
    request: ActionRequest
    state: ApprovalState
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by_session: str | None = None
    resulting_audit_id: int | None = None


class EngineConfigLike(Protocol):
    """The engine-config surface the decision pipeline actually reads.

    ``EngineConfig`` lives in ``executor``, which imports ``decision`` -- so
    ``decision`` cannot name the concrete class without a cycle. The previous
    workaround annotated the parameter as ``object``, which silenced the cycle by
    silencing the type checker: every attribute access on it was unchecked, and
    ``mypy --strict`` reported exactly that (ND-025). A Protocol keeps the
    dependency pointing one way and still checks the attributes.

    Members are declared read-only (properties, not variables): ``EngineConfig`` is
    a frozen dataclass, and a Protocol variable member is implicitly settable, which
    a frozen attribute cannot satisfy.
    """

    @property
    def approval_ttl_seconds(self) -> int: ...

    @property
    def connector_timeout_seconds(self) -> float: ...

    @property
    def tz(self) -> ZoneInfo: ...

    @property
    def audit_group_commit(self) -> int: ...

    @property
    def reservation_ttl_seconds(self) -> int: ...
