"""Guardrail data models and enums — the contract every other module depends on.

Pure data: no I/O, no DB. Requests are frozen; only persisted approval rows carry
mutable lifecycle state.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# A constrained recursive JSON value — keeps params typed under mypy --strict and
# makes the (untrusted) params surface explicit.
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


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


class CheckId(StrEnum):
    """Which check produced the decision — recorded for full explainability."""

    KILL_SWITCH = "kill_switch"
    DEFAULT_DENY = "default_deny"
    BOUNDS = "bounds"
    CAP_DAILY_RATE = "cap_daily_rate"
    CAP_EUR_DAY = "cap_eur_day"
    CAP_EUR_MONTH = "cap_eur_month"
    DRY_RUN = "dry_run"
    TIER_CONFIRM = "tier_confirm"
    NO_COMPENSATION = "no_compensating_command"
    OBSERVE = "observe"
    PASSED = "passed"
    EFFECT_FLOOR = "effect_floor"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTED = "executed"


class NumericBound(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: float | None = None
    max: float | None = None


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


class ParamEffectRule(BaseModel):
    """Deterministic rule: a parameter value matching a regex adds effects.

    For generic tools (http, shell) whose real-world effect depends on their
    arguments: `param` names the parameter, `pattern` is a full-match regex
    against its string form, `add_effects` are the labels gained on match.
    """

    model_config = ConfigDict(extra="forbid")
    param: str
    pattern: str
    add_effects: list[str]


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
    undo_window_seconds: int = 900
    requires_step_up: bool = False
    is_default_deny: bool = False


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


class ActionResult(BaseModel):
    """What evaluation produced."""

    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    decision: PolicyDecision
    executed: bool = False
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
