"""No deployed policy changes meaning because the engine was upgraded (ND-040 / U2).

R026 made this the acceptance for U2: **every existing policy's matches and
non-matches are byte-for-byte unchanged with the feature present but unused.** Opt-in
semantics, never a silent reinterpretation.

The risk is specific and worth stating plainly. `param_effects` rules are deployed in
customer policy files. Adding URL-typed matching to the same rule type means the
matcher now has two branches, and if the regex branch drifts even slightly -- a
different flag, a `search` where a `fullmatch` was, a coerced value -- then a rule
someone wrote a year ago starts labelling different actions, silently, with no policy
edit and no version bump on their side. A governance engine that quietly changes what
a deployed rule means is worse than one that never gained the feature.

So the corpus below asserts the regex branch is **the same function it always was**:
for every (pattern, value) pair, the engine's answer equals a direct
`re.fullmatch(pattern, str(value)) is not None`. The oracle is the original expression,
not a re-implementation of it, because a re-implementation could drift in the same
direction as the code it checks.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import yaml

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    EffectPolicy,
    ParamEffectRule,
    Policy,
    Source,
    Tier,
    UrlMatch,
)
from onedoor.store.db import Database

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))
REPO = Path(__file__).resolve().parents[2]

Matcher = Callable[[object], bool]

# Patterns drawn from the shipped policy files and the aliasing benchmark, plus forms
# chosen to stress the regex branch rather than to be easy.
CORPUS_PATTERNS = [
    r"https://(bank|pay)\.example\.com/.*",
    r".*(bank|pay)\.example\.com.*",
    r"https://.*",
    r".*",
    r"",
    r"[a-z]+",
    r"\d{3}",
    r"a|b",
    r"(?i)BANK\.example\.com",
    r"^anchored$",
    r"x*",
    r"(a)(b)?",
]

CORPUS_VALUES: list[object] = [
    "https://bank.example.com/transfer",
    "https://BANK.example.com/transfer",
    "https://bank%2Eexample%2Ecom/transfer",
    "https://t.co/x9k2",
    "https://203.0.113.7/transfer",
    "https://weather.example.com/today",
    "curl https://bank.example.com",
    "anchored",
    "abc",
    "123",
    "",
    "x",
    "a",
    "ab",
    0,
    1,
    True,
    3.5,
    ["a", "b"],
    {"k": "v"},
    None,
]


def _shipped_patterns() -> list[str]:
    """Every param_effects pattern actually shipped in this repository."""
    found: list[str] = []
    for path in sorted((REPO / "config").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for policy in raw.get("policies", []) or []:
            for rule in policy.get("param_effects", []) or []:
                if "pattern" in rule:
                    found.append(rule["pattern"])
    return found


def test_the_corpus_covers_what_is_actually_deployed() -> None:
    """A compatibility corpus that misses the shipped rules proves nothing."""
    for pattern in _shipped_patterns():
        assert pattern in CORPUS_PATTERNS, (
            f"a shipped policy uses pattern {pattern!r}, which the compatibility "
            f"corpus does not cover -- add it before trusting this suite"
        )


@contextmanager
def _engine(tmp_path: Path, rule: ParamEffectRule, name: str) -> Iterator[Matcher]:
    """Yield "did the ENGINE apply this rule's effect?" for a live policy store.

    The question is answered through `decide_and_reserve` rather than by calling a
    matcher directly, because it is the *deployed path* that must not change: a unit
    test of a helper would not notice if the pipeline stopped calling it. A temp file
    DB, not `:memory:`, for the reason `tests/conftest.py` gives -- WAL and triggers
    behave like production, and a second connection sees the same data.
    """
    database = Database(str(tmp_path / f"{name}.db"))
    database.init()
    conn = database.connect()
    try:
        policy_loader.upsert_effect(conn, EffectPolicy(effect="e", min_tier=Tier.CONFIRM))
        policy_loader.upsert(
            conn,
            Policy(
                action_type="demo.generic",
                tier=Tier.AUTO,
                dry_run=False,
                compensating_command="demo.generic",
                bounds=Bounds(strict_params=False),
                param_effects=[rule],
            ),
        )

        def matched(value: object) -> bool:
            outcome = decide_and_reserve(
                ActionRequest(
                    request_id=uuid4(),
                    action_type="demo.generic",
                    params={} if value is None else {"p": value},  # type: ignore[dict-item]
                    source=Source.LLM,
                    rationale="compat",
                    created_at=NOW,
                ),
                conn=conn,
                config=CONFIG,
                now=NOW,
            )
            # The effect floors the tier to CONFIRM, so a match means "not permitted".
            return not isinstance(outcome, PermittedIntent)

        yield matched
    finally:
        conn.close()


@pytest.mark.parametrize("pattern", CORPUS_PATTERNS)
def test_the_regex_branch_answers_exactly_as_it_always_did(tmp_path: Path, pattern: str) -> None:
    """The corpus assertion (R026), against the original expression as oracle."""
    rule = ParamEffectRule(param="p", pattern=pattern, add_effects=["e"])
    with _engine(tmp_path, rule, "corpus") as matched:
        for value in CORPUS_VALUES:
            expected = value is not None and re.fullmatch(pattern, str(value)) is not None
            actual = matched(value)
            assert actual == expected, (
                f"pattern {pattern!r} against {value!r}: engine said {actual}, "
                f"re.fullmatch says {expected}. A deployed rule changed meaning."
            )


def test_a_url_rule_is_opt_in_and_absent_by_default(tmp_path: Path) -> None:
    """The feature is present. A rule that does not ask for it does not get it."""
    rule = ParamEffectRule(param="p", pattern=r"https://bank\.example\.com/.*", add_effects=["e"])
    assert rule.url is None

    with _engine(tmp_path, rule, "optin") as matched:
        # The percent-encoded form is exactly what a URL rule would catch and a regex
        # rule would not. Under the regex rule it must STILL not match -- otherwise
        # the feature leaked into a policy that never asked for it.
        assert not matched("https://bank%2Eexample%2Ecom/transfer")
        assert matched("https://bank.example.com/transfer")


def test_a_rule_cannot_declare_both_matchers_or_neither() -> None:
    """A rule with two meanings has none that can be relied on."""
    with pytest.raises(ValueError, match="exactly one"):
        ParamEffectRule(param="p", pattern=".*", url=UrlMatch(hosts=["a.test"]), add_effects=["e"])
    with pytest.raises(ValueError, match="exactly one"):
        ParamEffectRule(param="p", add_effects=["e"])


def test_random_pattern_value_pairs_agree_with_the_oracle(tmp_path: Path) -> None:
    """Generated coverage, because a hand-picked corpus finds what it thought of."""
    rng = random.Random(20260822)
    alphabet = "ab.:/%1"
    for index in range(40):
        pattern = "".join(rng.choice(alphabet + "*+|()") for _ in range(rng.randint(1, 6)))
        try:
            re.compile(pattern)
        except re.error:
            continue  # an invalid pattern is a policy-load error, not a match question
        rule = ParamEffectRule(param="p", pattern=pattern, add_effects=["e"])
        values = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6))) for _ in range(4)]
        with _engine(tmp_path, rule, f"fuzz{index}") as matched:
            for value in values:
                expected = re.fullmatch(pattern, value) is not None
                assert matched(value) == expected, (
                    f"pattern {pattern!r} against {value!r} diverged from re.fullmatch"
                )
