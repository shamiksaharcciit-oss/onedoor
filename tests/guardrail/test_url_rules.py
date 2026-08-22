"""URL-typed effect rules, and what happens when a target cannot be read (U2, U3).

U1 built the canonicalizer and `tests/guardrail/test_urlcanon.py` tests it as a
function. These tests are about the **engine**: a policy declares a URL-typed rule, a
request arrives, and the verdict has to come out right through `decide_and_reserve` --
because a canonicalizer the pipeline forgets to call is worth nothing, and a unit test
of the canonicalizer would not notice.

Two behaviours are asserted here that the function-level tests cannot reach:

1. **Both directions on every concern** (acceptance item 6). An evasion is caught
   *and* the legitimate spelling still matches. A matcher that catches every evasion
   by matching nothing is not a fix.
2. **A target the canonicalizer refuses is a denial, not a crash and not a bypass**
   (U3). `decide_raw` deliberately does not swallow internal errors -- an exception
   from the policy store or the ledger propagates, because turning a bug into a
   routine denial would hide it. A malformed URL from a caller is *input*, not a bug,
   so it must be caught at the rule and turned into `malformed` explicitly. This is
   why U2 and U3 could not ship apart: adding the rule without the catch would mean a
   caller could crash the PDP with a bad URL.
"""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, decide_raw
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    CheckId,
    Decision,
    EffectPolicy,
    ParamEffectRule,
    Policy,
    Tier,
    UrlMatch,
)
from onedoor.guardrail.urlcanon import CANON_SCHEMA
from onedoor.store.db import Database
from tests.conftest import FROZEN_NOW, make_request

BANK = UrlMatch(hosts=["bank.example.com"], schemes=["https"])


def _seed(conn: Connection, url: UrlMatch = BANK, *, action: str = "url.http") -> None:
    """A generic HTTP tool whose effect depends on where it is pointed."""
    policy_loader.upsert_effect(
        conn, EffectPolicy(effect="money.egress.url", min_tier=Tier.CONFIRM)
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            param_effects=[ParamEffectRule(param="url", url=url, add_effects=["money.egress.url"])],
        ),
    )


def _verdict(conn: Connection, config: EngineConfig, value: object, action: str = "url.http"):  # type: ignore[no-untyped-def]
    request = make_request(action, {"url": value})
    return decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)


def _matched(conn: Connection, config: EngineConfig, value: object) -> bool:
    """Did the effect fire? The floor is CONFIRM, so a match is "not permitted"."""
    return not isinstance(_verdict(conn, config, value), PermittedIntent)


# Each pair is (spelling, why it is the same target). These are the strings a regex
# over `str(value)` gets wrong -- the disclosed gap, now closed at the rule.
SAME_TARGET = [
    ("https://bank.example.com/transfer", "the plain spelling"),
    ("https://BANK.example.com/transfer", "host case is not significant"),
    ("https://bank%2Eexample%2Ecom/transfer", "percent-encoding decodes to the same host"),
    ("https://bank.example.com./transfer", "a trailing dot is the same host to a resolver"),
    ("https://bank.example.com:443/transfer", ":443 is the https default"),
    ("HTTPS://bank.example.com/transfer", "scheme case is not significant"),
    ("  https://bank.example.com/transfer  ", "surrounding whitespace"),
]

# Strings that LOOK like the target to a substring or prefix reader and are not.
OTHER_TARGET = [
    ("https://bank.example.com@evil.test/transfer", "userinfo: the host is evil.test"),
    ("https://bank.example.com.evil.test/x", "a prefix, not the host"),
    ("https://notbank.example.com/transfer", "a different name that contains the target"),
    ("https://weather.example.com/today", "an innocent on the same action"),
    ("http://bank.example.com/transfer", "the scheme is declared and this is not it"),
    ("https://sub.bank.example.com/x", "a subdomain, which this rule did not ask for"),
]


@pytest.mark.parametrize(("spelling", "why"), SAME_TARGET)
def test_every_spelling_of_the_declared_target_matches(
    conn: Connection, config: EngineConfig, spelling: str, why: str
) -> None:
    _seed(conn)
    assert _matched(conn, config, spelling), f"{spelling!r} should reach the target: {why}"


@pytest.mark.parametrize(("spelling", "why"), OTHER_TARGET)
def test_lookalikes_do_not_match(
    conn: Connection, config: EngineConfig, spelling: str, why: str
) -> None:
    _seed(conn)
    assert not _matched(conn, config, spelling), f"{spelling!r} is a different target: {why}"


def test_subdomains_match_only_when_the_policy_says_so(
    conn: Connection, config: EngineConfig
) -> None:
    """The two readings disagree exactly where an attacker lives, so it is declared."""
    _seed(conn, UrlMatch(hosts=["example.com"], include_subdomains=True, schemes=["https"]))
    assert _matched(conn, config, "https://bank.example.com/transfer")
    assert _matched(conn, config, "https://example.com/transfer")
    # The label boundary is enforced, not assumed: this is a subdomain of evil.test.
    assert not _matched(conn, config, "https://example.com.evil.test/transfer")
    assert not _matched(conn, config, "https://notexample.com/transfer")


def test_an_ip_literal_matches_only_a_declared_network(
    conn: Connection, config: EngineConfig
) -> None:
    """Benchmark case 2. An IP literal is not a hostname and must not silently be one."""
    _seed(conn)  # hosts only, no cidrs
    assert not _matched(conn, config, "https://203.0.113.7/transfer")

    _seed(conn, UrlMatch(hosts=["bank.example.com"], cidrs=["203.0.113.0/24"], schemes=["https"]))
    assert _matched(conn, config, "https://203.0.113.7/transfer")
    # And the shorthand spellings of an address in range reach it too.
    assert _matched(conn, config, "https://0xcb.0.113.7/transfer")
    assert not _matched(conn, config, "https://198.51.100.7/transfer")
    # A name still matches by name; adding a CIDR did not turn the rule into one.
    assert _matched(conn, config, "https://bank.example.com/transfer")


def test_the_homograph_does_not_reach_the_target(conn: Connection, config: EngineConfig) -> None:
    """Cyrillic `а` encodes to punycode, which is visibly not the ASCII host."""
    _seed(conn)
    assert not _matched(conn, config, "https://bаnk.example.com/transfer")


def test_a_scheme_list_is_optional(conn: Connection, config: EngineConfig) -> None:
    """Declaring no scheme means the rule is about the host, whatever the scheme."""
    _seed(conn, UrlMatch(hosts=["bank.example.com"]))
    assert _matched(conn, config, "https://bank.example.com/transfer")
    assert _matched(conn, config, "http://bank.example.com/transfer")


# --- U3: a target that cannot be interpreted is refused, and says why -------------

UNREADABLE = [
    ("bank.example.com/transfer", "no scheme: the port and rules are undecidable"),
    ("https://bank%2Fevil.test/transfer", "percent-encoding hid a delimiter"),
    ("https://bank.example.com:notaport/x", "the port is not a number"),
    ("https://" + "a" * 300 + ".test/x", "a label longer than IDNA allows"),
    ("https:///transfer", "no host"),
    ("https://%2565vil.test/x", "doubly percent-encoded host"),
]


@pytest.mark.parametrize(("spelling", "why"), UNREADABLE)
def test_an_uninterpretable_url_is_denied_not_bypassed(
    conn: Connection, config: EngineConfig, spelling: str, why: str
) -> None:
    """A parse differential becomes a denial (scopegate), never a silent non-match.

    The failure direction matters more than the verdict: a non-match would let the
    action through *because* the string was too strange to read.
    """
    _seed(conn)
    result = _verdict(conn, config, spelling)
    assert not isinstance(result, PermittedIntent), why
    assert result.decision.decision is Decision.DENIED
    assert result.decision.reason_code is CheckId.MALFORMED


def test_a_non_string_url_is_denied_rather_than_stringified(
    conn: Connection, config: EngineConfig
) -> None:
    """A rule that stringifies whatever it is handed matches something else."""
    _seed(conn)
    for value in (12345, ["https://bank.example.com/"], {"url": "https://bank.example.com/"}):
        result = _verdict(conn, config, value)
        assert not isinstance(result, PermittedIntent)
        assert result.decision.reason_code is CheckId.MALFORMED


def test_the_denial_records_which_malformed_it_was(conn: Connection, config: EngineConfig) -> None:
    """R013's condition: the evidence separates malformed-URL from malformed-JSON.

    Without this the reason code is one bucket holding a broken client and someone
    probing the effect matcher, and an operator reading a spike cannot tell them
    apart. The canonicalizer's identity rides along for the same reason
    `snapshot_schema` does: a verdict that depends on a normalisation depends on
    *which* normalisation.
    """
    _seed(conn)
    result = _verdict(conn, config, "https://bank%2Fevil.test/transfer")
    assert result.audit_id is not None
    row = conn.execute(
        "SELECT reason_code, malformed_kind, canon_schema FROM actions_audit WHERE id=?",
        (result.audit_id,),
    ).fetchone()
    assert row["reason_code"] == CheckId.MALFORMED.value
    assert row["malformed_kind"] == "url_canonicalization"
    assert row["canon_schema"] == CANON_SCHEMA


def test_ordinary_verdicts_carry_no_canonicalization_evidence(
    conn: Connection, config: EngineConfig
) -> None:
    """Absent means "no canonicalization was involved" -- not "unknown" (R015)."""
    _seed(conn)
    result = _verdict(conn, config, "https://weather.example.com/today")
    assert isinstance(result, PermittedIntent)
    row = conn.execute(
        "SELECT malformed_kind, canon_schema FROM actions_audit WHERE id=?",
        (result.intent_audit_id,),
    ).fetchone()
    assert row["malformed_kind"] is None
    assert row["canon_schema"] is None


def test_a_malformed_url_denies_even_though_the_kill_switch_would_propose(
    conn: Connection, config: EngineConfig
) -> None:
    """Declared, not accidental: an unreadable input denies rather than proposing.

    The kill switch clamps executable tiers to propose-only, but a proposal is a
    request to a human to approve *this action* -- and the engine cannot say what
    this action is. Bounds already behaves this way (an out-of-bounds action is
    denied, never proposed); the same argument reaches an unreadable target.
    """
    from onedoor.guardrail import killswitch
    from onedoor.store.db import tx

    _seed(conn)
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = _verdict(conn, config, "https://bank%2Fevil.test/transfer")
    assert result.decision.decision is Decision.DENIED
    assert result.decision.reason_code is CheckId.MALFORMED


def test_the_url_rule_does_not_break_the_envelope_malformed_path(
    conn: Connection, config: EngineConfig
) -> None:
    """The other malformed still denies, and is still a different event."""
    _seed(conn)
    result = decide_raw({"action_type": "url.http"}, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.reason_code is CheckId.MALFORMED
    # It writes no audit row at all -- no policy and no request object exist yet. A
    # pre-existing gap in the ledger, recorded here so the asymmetry with the URL
    # denial above is visible rather than surprising.
    assert result.audit_id is None


# --- The deployer-facing surface: a URL rule is written in a policy file ----------

URL_POLICY_YAML = """
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
"""


def test_a_url_rule_can_be_authored_in_a_policy_file(
    db: Database, config: EngineConfig, tmp_path: Path
) -> None:
    """It is not a feature if it can only be built in Python."""
    path = tmp_path / "url.yaml"
    path.write_text(URL_POLICY_YAML, encoding="utf-8")
    conn = db.connect()
    try:
        assert policy_loader.load_file(conn, path) == 1
        assert _matched(conn, config, "https://bank%2Eexample%2Ecom/transfer")
        assert not _matched(conn, config, "https://bank.example.com@evil.test/x")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("block", "why"),
    [
        ("hosts: ['not a host']", "uninterpretable host"),
        ("cidrs: ['203.0.113.0/99']", "invalid CIDR"),
        ("schemes: [https]", "neither hosts nor cidrs"),
    ],
)
def test_an_unusable_url_rule_is_rejected_when_the_policy_is_written(
    db: Database, tmp_path: Path, block: str, why: str
) -> None:
    """An authoring error surfaces at load, not as a stream of runtime denials.

    `why` is matched against the message, not just the exception type: a test that
    accepts any ValueError passes when the policy fails to load for a reason that
    has nothing to do with the rule.
    """
    path = tmp_path / "bad.yaml"
    body = URL_POLICY_YAML.replace("hosts: [bank.example.com]\n          schemes: [https]", block)
    path.write_text(body, encoding="utf-8")
    conn = db.connect()
    try:
        with pytest.raises(ValueError, match=why):
            policy_loader.load_file(conn, path)
    finally:
        conn.close()
