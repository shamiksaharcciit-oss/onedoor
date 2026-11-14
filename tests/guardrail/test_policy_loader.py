from __future__ import annotations

import re
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.policy import PolicyStore
from tests.conftest import _CONFIG_DIR

_DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"


def test_seed_file_is_idempotent(conn: Connection) -> None:
    before = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    policy_loader.load_file(conn, _CONFIG_DIR / "policies.yaml")
    after = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    assert before == after  # re-loading changes nothing


def test_tier1_without_compensation_is_rejected(conn: Connection, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "policies:\n  - action_type: bad.action\n    tier: 1\n    dry_run: false\n",
        encoding="utf-8",
    )
    count_before = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    with pytest.raises(ValueError, match="compensating_command"):
        policy_loader.load_file(conn, bad)
    # Fail-closed: nothing was written.
    count_after = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    assert count_before == count_after


def test_bounds_and_caps_round_trip(conn: Connection) -> None:
    policy = PolicyStore().get(conn, "demo.toggle")
    assert policy.bounds.required == ["target", "state"]
    assert policy.compensating_command == "demo.restore"
    capped = PolicyStore().get(conn, "demo.capped")
    assert capped.caps.daily_rate == 2


def test_a_compensating_command_naming_nothing_is_rejected(
    conn: Connection, tmp_path: Path
) -> None:
    """An undo of this action would have nowhere to go -- caught when the
    policy loads, not only when an operator actually attempts the undo."""
    bad = tmp_path / "bad_reversal.yaml"
    bad.write_text(
        "policies:\n"
        "  - action_type: ghost.action\n"
        "    tier: 1\n"
        "    dry_run: false\n"
        "    compensating_command: ghost.nowhere\n",
        encoding="utf-8",
    )
    count_before = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    with pytest.raises(ValueError, match="compensating_command 'ghost.nowhere'"):
        policy_loader.load_file(conn, bad)
    count_after = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    assert count_before == count_after  # fail-closed: nothing was written


def test_two_policies_naming_each_other_as_their_own_reversal_both_load(
    conn: Connection, tmp_path: Path
) -> None:
    """The common shape -- A's reversal is B, B's reversal is A -- must
    validate regardless of which one happens to be checked first, since
    neither exists in the table yet when the file is loaded."""
    pair = tmp_path / "pair.yaml"
    pair.write_text(
        "policies:\n"
        "  - action_type: pair.forward\n"
        "    tier: 1\n"
        "    dry_run: false\n"
        "    compensating_command: pair.reverse\n"
        "  - action_type: pair.reverse\n"
        "    tier: 1\n"
        "    dry_run: false\n"
        "    compensating_command: pair.forward\n",
        encoding="utf-8",
    )
    assert policy_loader.load_file(conn, pair) == 2


def test_a_reversal_already_in_the_table_satisfies_a_new_policy(
    conn: Connection, tmp_path: Path
) -> None:
    """A policy's own reversal need not be declared in the SAME file -- one
    already loaded (here, the real config's own `demo.restore`) satisfies it
    too."""
    extra = tmp_path / "extra.yaml"
    extra.write_text(
        "policies:\n"
        "  - action_type: extra.action\n"
        "    tier: 1\n"
        "    dry_run: false\n"
        "    compensating_command: demo.restore\n",
        encoding="utf-8",
    )
    assert policy_loader.load_file(conn, extra) == 1


def test_upsert_called_directly_does_not_check_the_reversal_target() -> None:
    """`upsert`'s own direct `validate_policy` call passes no
    `known_action_types` -- it validates one policy with no view of what
    else exists, so it cannot reject one for a fact it has no way to know.
    `load_file` is where this check actually runs."""
    from onedoor.guardrail.models import Bounds, Policy, Tier

    policy = Policy(
        action_type="solo.action",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="solo.nowhere",
        bounds=Bounds(strict_params=False),
    )
    policy_loader.validate_policy(policy)  # must not raise


def test_an_empty_compensating_command_is_not_a_dangling_reversal() -> None:
    """A policy that declares `compensating_command=""` means it has none --
    the same falsy check the presence rule above already uses -- not a
    target to resolve. A fixture using the empty string for "no reversal"
    (an OBSERVE action, which needs none at all) must load regardless of
    what `known_action_types` does or does not contain, including an empty
    set."""
    from onedoor.guardrail.models import Bounds, Policy, Tier

    policy = Policy(
        action_type="reports.read",
        tier=Tier.OBSERVE,
        dry_run=False,
        compensating_command="",
        bounds=Bounds(strict_params=False),
    )
    policy_loader.validate_policy(policy, known_action_types=frozenset())  # must not raise


def test_the_policy_reference_names_the_real_load_and_decision_time_behavior() -> None:
    """`docs/policy-reference.md`'s own compensating_command field note once
    said the named action type is "not checked to exist, at load time or at
    decision time" -- true before this round, false after it (`load_file`
    now refuses an undeclared target). A doc that still said so would send an
    operator looking for a safety net that `load_file` already provides, or
    away from the gap that genuinely remains (a policy loaded through
    `upsert` directly, bypassing that check). Pinned here rather than left to
    drift again the way the vocabulary list once did (see
    `test_reason_vocabulary.py`'s own history of the same failure mode)."""
    doc = (_DOCS_ROOT / "policy-reference.md").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", doc)  # line-wrap-proof: word boundaries only

    # The corrected claims, word for word (modulo wrapping).
    assert (
        "`load_file` — the batch loader run at boot — refuses a policy whose "
        "compensating_command names no action type anywhere in the table or "
        "the same file"
    ) in flat
    assert "does **not** check this" in flat
    assert "denied exactly like any other unregistered action type" in flat
    assert "default_deny" in flat

    # The superseded claim must not survive anywhere in the current text.
    assert not re.search(r"not checked to exist, at load time or at decision time", flat)
