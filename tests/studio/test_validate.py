"""`onedoor.studio.validate.problems`: `validate_policy`'s own refusals,
collected instead of raised at the first one."""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.studio import validate


def _restore() -> Policy:
    return Policy(
        action_type="demo.restore",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        bounds=Bounds(strict_params=False),
    )


def _dangling() -> Policy:
    return Policy(
        action_type="demo.ghost",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.nowhere",
        bounds=Bounds(strict_params=False),
    )


def test_a_dangling_reversal_is_invisible_with_no_known_action_types() -> None:
    """The documented limitation, unchanged: with nothing to check against,
    `problems` cannot see a `compensating_command` naming an action the
    candidate does not define -- the same gap the module's own docstring
    already names."""
    found = validate.problems([_dangling()])
    assert found == []


def test_a_dangling_reversal_is_found_when_known_action_types_is_given() -> None:
    found = validate.problems([_dangling()], known_action_types=frozenset({"demo.ghost"}))
    assert len(found) == 1
    assert found[0].action_type == "demo.ghost"
    assert "demo.nowhere" in found[0].message


def test_known_action_types_for_unions_the_live_table_and_the_candidate(
    conn: Connection,
) -> None:
    policy_loader.upsert(conn, _restore())
    known = validate.known_action_types_for(conn, [_dangling()])
    assert "demo.restore" in known  # already in the live table
    assert "demo.ghost" in known  # the candidate's own action type
    assert "demo.nowhere" not in known  # the undeclared target itself


def test_a_candidate_whose_reversal_is_already_live_has_no_problem(
    conn: Connection,
) -> None:
    """A candidate naming a reversal already in the live table -- not itself
    part of the candidate -- is not a dangling reference."""
    policy_loader.upsert(conn, _restore())
    candidate = [
        Policy(
            action_type="demo.pay",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        )
    ]
    known = validate.known_action_types_for(conn, candidate)
    found = validate.problems(candidate, known_action_types=known)
    assert found == []


def test_a_mutual_pair_in_one_candidate_has_no_problem(conn: Connection) -> None:
    candidate = [
        Policy(
            action_type="demo.forward",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.reverse",
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="demo.reverse",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.forward",
            bounds=Bounds(strict_params=False),
        ),
    ]
    known = validate.known_action_types_for(conn, candidate)
    assert validate.problems(candidate, known_action_types=known) == []
