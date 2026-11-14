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


class NeedsMoreApprovers(ApprovalError):
    """`approvals.cas_approve` or `plans.approve` recorded this approver, but
    the policy's own two-person rule needs at least one more, different,
    identity before the row flips to approved/active -- a subclass of
    `ApprovalError`, so every caller that already catches the parent class
    handles this the same way it handles any other "not ready yet" CAS
    outcome. The approver's own call still succeeded (recorded); only
    resumption is not yet due. `subject_id` is the approval or plan id,
    whichever raised this."""

    def __init__(
        self, subject_id: int, *, required: int, recorded: int, kind: str = "approval"
    ) -> None:
        super().__init__(
            f"{kind} {subject_id} recorded {recorded} of {required} required "
            f"approvers; needs a different identity to approve as well"
        )
        self.subject_id = subject_id
        self.required = required
        self.recorded = recorded


class PlanError(GuardrailError):
    """A plan's own shape does not match what it claims to cover -- e.g. it
    names no `amount_param`/`recipient_param` for an action whose policy
    bounds that amount or recipient, which would let the plan's own ceiling
    apply to nothing."""


class UndoError(GuardrailError):
    """An undo could not be performed (window expired, already undone, no reversal)."""


class ReportError(GuardrailError):
    """A `/v1/report` body asserts something the outcome vocabulary does not allow.

    Currently unraised: the one case this existed for -- `no_effect=True` on an
    outcome other than `failure` -- is accepted and ignored as of 0.8.1, not
    refused (AADP -03 §4.1 requires a PDP to ignore it there, not reject the
    report). Kept for a future outcome-vocabulary violation that does need a
    hard refusal.
    """
