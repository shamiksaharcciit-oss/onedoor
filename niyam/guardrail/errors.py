"""Typed exceptions for the guardrail engine."""

from __future__ import annotations


class GuardrailError(Exception):
    """Base class for all guardrail errors."""


class PolicyError(GuardrailError):
    """A policy is malformed or violates an invariant (e.g. Tier 1 without undo)."""


class KillSwitchEngaged(GuardrailError):
    """Raised where a caller explicitly asserts the kill switch must be disengaged."""


class CapExceeded(GuardrailError):
    """A per-action-type cap would be exceeded."""


class ConnectorFailure(GuardrailError):
    """A connector ``act_*`` call failed or timed out (handled fail-soft)."""


class AuditImmutabilityError(GuardrailError):
    """An attempt to UPDATE or DELETE the append-only audit log."""


class ApprovalError(GuardrailError):
    """An approval could not be transitioned (expired, already decided, unauthorized)."""


class UndoError(GuardrailError):
    """An undo could not be performed (window expired, already undone, no reversal)."""
