"""The simulated tool: deterministic, in-memory, no model and no network.

Every action type the eval's policies declare maps to one effect kind here. A
call records what happened -- money moved, rows deleted, a message sent -- and
returns the outcome the caller would observe. ``tool_outcome`` scripts the
observed outcome independently of onedoor's own decision: a ``timeout`` means
the tool actually acted but the caller's response was lost (the dangerous
case a naive retry duplicates); a ``failure`` means the tool never acted at
all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Effect:
    """One real-world effect the simulated tool recorded."""

    action_type: str
    kind: str  # money_moved | rows_deleted | message_sent | read | none
    detail: dict[str, Any]


@dataclass
class SimulatedTool:
    """One instance per scenario run (fresh, so effects never leak between
    scenarios or between the without/with-onedoor sides of the same one)."""

    effects: list[Effect] = field(default_factory=list)

    def call(self, action_type: str, params: dict[str, Any], *, tool_outcome: str) -> str:
        """Returns the outcome the caller observes: "success", "timeout" or
        "failure". Appends an :class:`Effect` to ``self.effects`` iff the tool
        actually acted -- which happens on "success" and, silently, on
        "timeout" too (profile: acted, then the response was lost)."""
        if tool_outcome == "failure":
            return "failure"
        self.effects.append(Effect(action_type, *effect_of(action_type, params)))
        return tool_outcome  # "success" or "timeout"


def effect_of(action_type: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if action_type in ("payments.transfer", "refunds.issue", "payments.reverse"):
        return "money_moved", {
            "amount_eur": params.get("amount_eur"),
            "destination_account": params.get("destination_account"),
        }
    if action_type == "payouts.schedule":
        return "money_moved", {"batch_id": params.get("batch_id")}
    if action_type == "records.delete":
        return "rows_deleted", {
            "table": params.get("table"),
            "record_id": params.get("record_id"),
        }
    if action_type == "messages.send":
        return "message_sent", {
            "recipient": params.get("recipient"),
            "body": params.get("body"),
        }
    if action_type == "webhooks.post":
        return "message_sent", {"url": params.get("url"), "payload_id": params.get("payload_id")}
    if action_type == "ledger.read":
        return "read", {"account_id": params.get("account_id")}
    return "none", {}
