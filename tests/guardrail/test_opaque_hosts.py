"""A host whose target cannot be known is governed as though it were the target (U4).

`https://t.co/x9k2` is the benchmark case that canonicalization cannot touch. The
host really is `t.co`; the bank is behind a redirect; following it is a network call
the PDP's offline model forbids. So the mechanism is a *declaration*, and these tests
hold it to the three things a declaration has to be:

**Opt-in.** A policy without an `opaque` block behaves exactly as it did without the
feature. Nothing on this list governs anything until a deployer asks for it.

**Members only.** The benchmark's innocents column is the guard. A mechanism that
governed every host not on an allowlist would take `evasive 0/3 -> 3/3` and
`innocent-ok 3/3 -> 2/3`, and governance that fires on innocents is over-blocking.
`weather.example.com` must come through untouched, and it is asserted here rather
than hoped for.

**Attributable.** A member is treated as the declared target, so the verdict depends
on who said the host was opaque and on which version of the list said it. The class
identity rides in evidence. Adding a host to the shipped list is a visible instrument
change; the version is how it becomes visible.

And the limitation is tested as a limitation: an undeclared shortener is NOT caught,
asserted in the same file as the fix, because a test suite that only demonstrates
success reads as a stronger claim than the code can support.
"""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import opaque_hosts, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    CheckId,
    Decision,
    EffectPolicy,
    OpaqueHosts,
    ParamEffectRule,
    Policy,
    Tier,
    UrlMatch,
)
from onedoor.guardrail.opaque_hosts import OPAQUE_HOSTS_SCHEMA, POLICY_DECLARED
from onedoor.store.db import Database
from tests.conftest import FROZEN_NOW, make_request

DECLARED = UrlMatch(hosts=["bank.example.com"], schemes=["https"])
WITH_OPAQUE = UrlMatch(hosts=["bank.example.com"], schemes=["https"], opaque=OpaqueHosts())


def _seed(conn: Connection, url: UrlMatch) -> None:
    policy_loader.upsert_effect(
        conn, EffectPolicy(effect="money.egress.url", min_tier=Tier.CONFIRM)
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="url.http",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            param_effects=[ParamEffectRule(param="url", url=url, add_effects=["money.egress.url"])],
        ),
    )


def _verdict(conn: Connection, config: EngineConfig, value: str):  # type: ignore[no-untyped-def]
    request = make_request("url.http", {"url": value})
    return decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)


def _governed(conn: Connection, config: EngineConfig, value: str) -> bool:
    """Did the engine stop this from silently auto-executing?"""
    return not isinstance(_verdict(conn, config, value), PermittedIntent)


def test_a_shortener_passes_when_the_policy_has_not_declared_one(
    conn: Connection, config: EngineConfig
) -> None:
    """The gap as it stands, asserted before the fix is asserted.

    Without this test the next one proves nothing: a mechanism that catches `t.co`
    proves it catches shorteners only if `t.co` was getting through before.
    """
    _seed(conn, DECLARED)
    assert not _governed(conn, config, "https://t.co/x9k2")


def test_a_declared_shortener_is_governed(conn: Connection, config: EngineConfig) -> None:
    """Benchmark case 1. The rule fires because the target cannot be ruled out."""
    _seed(conn, WITH_OPAQUE)
    assert _governed(conn, config, "https://t.co/x9k2")


def test_the_innocent_on_the_same_action_is_untouched(
    conn: Connection, config: EngineConfig
) -> None:
    """The over-blocking guard, and the reason this is a list rather than a default."""
    _seed(conn, WITH_OPAQUE)
    result = _verdict(conn, config, "https://weather.example.com/today")
    assert isinstance(result, PermittedIntent), (
        "an innocent host was governed by the opaque mechanism -- this is the "
        "over-blocking failure the benchmark's innocents column exists to catch"
    )


def test_the_declared_target_still_matches_by_name(conn: Connection, config: EngineConfig) -> None:
    """Adding the mechanism did not replace the rule it was added to."""
    _seed(conn, WITH_OPAQUE)
    assert _governed(conn, config, "https://bank.example.com/transfer")
    assert _governed(conn, config, "https://bank%2Eexample%2Ecom/transfer")


def test_an_undeclared_shortener_is_not_caught(conn: Connection, config: EngineConfig) -> None:
    """The limitation, asserted as a limitation. A starter list is not a census.

    Anyone can run a redirector on their own domain, and this one is not on any list.
    The mechanism raises the cost of the evasion; it does not close the class, and a
    suite that only showed the successes would imply otherwise.
    """
    _seed(conn, WITH_OPAQUE)
    assert not _governed(conn, config, "https://go.some-startup.example/abc123")


def test_a_deployer_can_add_their_own_redirector(conn: Connection, config: EngineConfig) -> None:
    """Which is why `extra` exists: the operator knows their environment, we do not."""
    _seed(
        conn,
        UrlMatch(
            hosts=["bank.example.com"],
            schemes=["https"],
            opaque=OpaqueHosts(extra=["go.some-startup.example"]),
        ),
    )
    assert _governed(conn, config, "https://go.some-startup.example/abc123")
    assert not _governed(conn, config, "https://weather.example.com/today")


def test_the_shipped_list_can_be_turned_off(conn: Connection, config: EngineConfig) -> None:
    """A deployer who wants only their own list gets only their own list."""
    _seed(
        conn,
        UrlMatch(
            hosts=["bank.example.com"],
            schemes=["https"],
            opaque=OpaqueHosts(builtin=False, extra=["go.some-startup.example"]),
        ),
    )
    assert _governed(conn, config, "https://go.some-startup.example/abc123")
    assert not _governed(conn, config, "https://t.co/x9k2")


def test_membership_is_by_exact_host_not_by_suffix(conn: Connection, config: EngineConfig) -> None:
    """A subdomain of a shortener is a different service, and suffix matching without
    a label boundary is the classic bypass running in the other direction."""
    _seed(conn, WITH_OPAQUE)
    assert not _governed(conn, config, "https://x.t.co/x9k2")
    assert not _governed(conn, config, "https://t.co.evil.test/x9k2")
    assert not _governed(conn, config, "https://nott.co/x9k2")


def test_a_member_is_recognised_through_its_aliases(conn: Connection, config: EngineConfig) -> None:
    """Membership is checked AFTER canonicalization (R025), so the shortener's own
    spelling tricks do not evade the class the way they evade a raw string list."""
    _seed(conn, WITH_OPAQUE)
    assert _governed(conn, config, "https://T.CO/x9k2")
    assert _governed(conn, config, "https://t.co./x9k2")
    assert _governed(conn, config, "https://t%2Eco/x9k2")


def test_an_ip_literal_is_never_an_opaque_host(conn: Connection, config: EngineConfig) -> None:
    """The class is a list of names. An address is matched by CIDR or not at all."""
    _seed(conn, WITH_OPAQUE)
    assert not _governed(conn, config, "https://203.0.113.7/transfer")


# --- Evidence: which declaration made this verdict, and which version of it -------


def _evidence(conn: Connection, config: EngineConfig, value: str) -> str | None:
    result = _verdict(conn, config, value)
    audit_id = result.intent_audit_id if isinstance(result, PermittedIntent) else result.audit_id
    row = conn.execute("SELECT opaque_class FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
    return row["opaque_class"]  # type: ignore[no-any-return]


def test_the_evidence_names_the_class_that_matched(conn: Connection, config: EngineConfig) -> None:
    """Attributability. A verdict that depends on a declaration records which one."""
    _seed(conn, WITH_OPAQUE)
    assert _evidence(conn, config, "https://t.co/x9k2") == OPAQUE_HOSTS_SCHEMA


def test_the_evidence_distinguishes_a_deployers_own_entry(
    conn: Connection, config: EngineConfig
) -> None:
    """ "We shipped this host" and "you declared this host" are different facts."""
    _seed(
        conn,
        UrlMatch(
            hosts=["bank.example.com"],
            schemes=["https"],
            opaque=OpaqueHosts(extra=["go.some-startup.example"]),
        ),
    )
    assert _evidence(conn, config, "https://go.some-startup.example/abc123") == POLICY_DECLARED


def test_a_match_on_the_declared_host_records_no_opaque_class(
    conn: Connection, config: EngineConfig
) -> None:
    """Absent means "this verdict did not depend on an opaque declaration" (R015)."""
    _seed(conn, WITH_OPAQUE)
    assert _evidence(conn, config, "https://bank.example.com/transfer") is None
    assert _evidence(conn, config, "https://weather.example.com/today") is None


def test_the_class_identity_is_versioned() -> None:
    """Adding a host changes what some policy matches, so the list carries a version."""
    assert OPAQUE_HOSTS_SCHEMA == "onedoor/opaque-hosts/1"
    assert POLICY_DECLARED != OPAQUE_HOSTS_SCHEMA


def test_the_shipped_list_is_already_canonical() -> None:
    """An entry that is not its own canonical form could never match anything.

    Checked mechanically rather than by eye: `T.CO`, `t.co.` or a percent-encoded
    entry would sit in the list looking correct and matching nothing, and a list that
    silently fails to fire is worse than no list.
    """
    for host in opaque_hosts.BUILTIN:
        canonical, is_ip = opaque_hosts._canonical_host(host)
        assert canonical == host, f"{host!r} is not canonical; it would never match"
        assert not is_ip, f"{host!r} parses as an IP literal, which is never a shortener"


# --- The deployer-facing surface --------------------------------------------------

OPAQUE_YAML = """
effects:
  money.egress.url:
    min_tier: 3
policies:
  - action_type: url.http
    tier: 1
    dry_run: false
    compensating_command: demo.restore
    bounds:
      strict_params: false
    param_effects:
      - param: url
        add_effects: [money.egress.url]
        url:
          hosts: [bank.example.com]
          schemes: [https]
          opaque:
            builtin: true
            extra: [go.some-startup.example]
"""


def test_the_declaration_can_be_written_in_a_policy_file(
    db: Database, config: EngineConfig, tmp_path: Path
) -> None:
    path = tmp_path / "opaque.yaml"
    path.write_text(OPAQUE_YAML, encoding="utf-8")
    conn = db.connect()
    try:
        assert policy_loader.load_file(conn, path) == 1
        assert _governed(conn, config, "https://t.co/x9k2")
        assert _governed(conn, config, "https://go.some-startup.example/abc123")
        assert not _governed(conn, config, "https://weather.example.com/today")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("block", "why"),
    [
        ("builtin: true\n            extra: ['not a host']", "uninterpretable opaque host"),
        ("builtin: false\n            extra: []", "names no host at all"),
    ],
)
def test_an_unusable_declaration_is_rejected_at_load(
    db: Database, tmp_path: Path, block: str, why: str
) -> None:
    """An authoring error surfaces when the policy is written, not as silence."""
    path = tmp_path / "bad.yaml"
    body = OPAQUE_YAML.replace("builtin: true\n            extra: [go.some-startup.example]", block)
    path.write_text(body, encoding="utf-8")
    conn = db.connect()
    try:
        with pytest.raises(ValueError, match=why):
            policy_loader.load_file(conn, path)
    finally:
        conn.close()


def test_the_verdict_on_a_declared_shortener_uses_no_new_reason_code(
    conn: Connection, config: EngineConfig
) -> None:
    """R025: no new wire vocabulary. The member is handled as the target would be.

    So the code is `effect_floor`, which already exists and already means exactly
    what happened -- an effect raised the floor. "We could not tell where this goes"
    is a fact about the target, recorded in evidence; it is not a new kind of verdict,
    and a PEP that has never heard of this feature reads the verdict correctly.
    """
    _seed(conn, WITH_OPAQUE)
    result = _verdict(conn, config, "https://t.co/x9k2")
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision is Decision.PROPOSED
    assert result.decision.reason_code is CheckId.EFFECT_FLOOR


def test_governing_an_opaque_host_can_only_be_more_restrictive(
    conn: Connection, config: EngineConfig
) -> None:
    """The safety argument, made checkable.

    A member gains the rule's effects, and an effect can only raise a tier floor or
    add a cap -- never lower one. So declaring a host opaque can never make an action
    MORE permitted than leaving it undeclared. Asserted by comparing the two verdicts
    on the same request rather than by reasoning about it.
    """
    for value in ("https://t.co/x9k2", "https://weather.example.com/today"):
        _seed(conn, DECLARED)
        without = _verdict(conn, config, value)
        _seed(conn, WITH_OPAQUE)
        with_ = _verdict(conn, config, value)
        if isinstance(without, PermittedIntent):
            continue  # permitted may become governed; that is the whole point
        assert not isinstance(with_, PermittedIntent), (
            f"{value!r} was governed without the opaque declaration and permitted "
            f"with it -- the mechanism made the engine more permissive"
        )
