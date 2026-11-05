from __future__ import annotations

from eval.harness.tool import SimulatedTool


def test_success_records_one_effect() -> None:
    tool = SimulatedTool()
    outcome = tool.call(
        "payments.transfer", {"amount_eur": 10, "destination_account": "a"}, tool_outcome="success"
    )
    assert outcome == "success"
    assert len(tool.effects) == 1
    assert tool.effects[0].kind == "money_moved"


def test_a_timeout_still_records_an_effect() -> None:
    """The dangerous case: the tool acted, but the caller only learns "timeout"."""
    tool = SimulatedTool()
    outcome = tool.call("messages.send", {"recipient": "a", "body": "b"}, tool_outcome="timeout")
    assert outcome == "timeout"
    assert len(tool.effects) == 1
    assert tool.effects[0].kind == "message_sent"


def test_a_clean_failure_records_no_effect() -> None:
    tool = SimulatedTool()
    outcome = tool.call(
        "payments.transfer", {"amount_eur": 10, "destination_account": "a"}, tool_outcome="failure"
    )
    assert outcome == "failure"
    assert tool.effects == []


def test_an_unknown_action_type_records_no_effect_kind() -> None:
    tool = SimulatedTool()
    tool.call("something.unmapped", {}, tool_outcome="success")
    assert tool.effects[0].kind == "none"


def test_a_read_records_a_read_effect() -> None:
    tool = SimulatedTool()
    tool.call("ledger.read", {"account_id": "a"}, tool_outcome="success")
    assert tool.effects[0].kind == "read"
