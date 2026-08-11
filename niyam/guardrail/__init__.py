"""The guardrail engine — the deterministic core of Sutradhar.

Every action from every source (scheduler, rule, LLM, UI) flows through here.
The public surface is intentionally tiny: build a request with
:func:`propose_action` (or an explicit :class:`ActionRequest`) and evaluate it
with :func:`evaluate_and_execute`. Nothing outside this package may import
connector ``act_*`` functions — only :mod:`app.guardrail.executor` may, via the
injected :class:`ConnectorRegistry`.
"""

from __future__ import annotations

from niyam.guardrail.errors import (
    AuditImmutabilityError,
    CapExceeded,
    GuardrailError,
    KillSwitchEngaged,
)
from niyam.guardrail.executor import evaluate_and_execute, propose_action
from niyam.guardrail.models import (
    ActionRequest,
    ActionResult,
    Approval,
    ApprovalState,
    Bounds,
    Caps,
    CheckId,
    Decision,
    Policy,
    PolicyDecision,
    Source,
    Tier,
)
from niyam.guardrail.registry import ConnectorRegistry

__all__ = [
    "ActionRequest",
    "ActionResult",
    "Approval",
    "ApprovalState",
    "AuditImmutabilityError",
    "Bounds",
    "CapExceeded",
    "Caps",
    "CheckId",
    "ConnectorRegistry",
    "Decision",
    "GuardrailError",
    "KillSwitchEngaged",
    "Policy",
    "PolicyDecision",
    "Source",
    "Tier",
    "evaluate_and_execute",
    "propose_action",
]
