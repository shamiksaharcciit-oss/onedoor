"""ND-040's acceptance, measured by the instrument that disclosed the gap (U5).

R024 fixed the acceptance before the code was written: the benchmark's three
URL-shaped evasive cases go **0/3 -> 3/3**, with **ND-048's shell case asserted still
failing** in the same test. A negative acceptance criterion is the honest counterpart
to a positive one -- without it, "evasive improved" reads as "evasion closed", which
is the overstatement the ND-040 disclosure already had to correct once.

These assertions run in CI rather than living in a printed table, because a claim in
a README that nothing re-checks is a claim with a shelf life. The three guards that
matter, in order of how easy they would be to lose:

1. **`innocent-ok` stays 3/3.** Non-negotiable. The opaque-host mechanism is exactly
   what could break it, and governance that fires on innocents is over-blocking.
2. **The shell case stays uncaught.** If someone later makes it pass by widening a
   rule, this test fails and forces the disclosure to be rewritten deliberately.
3. **L2 is unchanged.** ND-040 added L3 beside L2 rather than editing it. A fix that
   edits the baseline it is measured against has destroyed its own evidence.
"""

from __future__ import annotations

import pytest

from experiments.aliasing_benchmark import (
    Case,
    build_cases,
    governed_verdict,
    make_engine,
)

URL_EVASIVE = "url"
SHELL_EVASIVE = "shell"


def _score(layer: str) -> dict[str, str]:
    """Re-run the benchmark's own tallying for one layer. No new judgement here."""
    conn, config = make_engine(layer)
    try:
        tallies: dict[str, list[int]] = {}
        for case in build_cases():
            caught = governed_verdict(conn, config, case)
            t = tallies.setdefault(case.kind, [0, 0])
            t[1] += 1
            t[0] += caught if case.true_effect else not caught
    finally:
        conn.close()
    return {kind: f"{hit}/{total}" for kind, (hit, total) in tallies.items()}


def _evasive_by_shape() -> tuple[list[Case], list[Case]]:
    """Split the evasive set the way the survey did: URL-shaped, and not."""
    evasive = [c for c in build_cases() if c.kind == "generic_evasive"]
    return (
        [c for c in evasive if c.action_type == "net.http"],
        [c for c in evasive if c.action_type == "sys.shell"],
    )


def test_the_three_url_shaped_evasions_went_from_none_to_all() -> None:
    """R024's acceptance, in one assertion each way."""
    url_cases, _ = _evasive_by_shape()
    assert len(url_cases) == 3, "the benchmark's URL-shaped evasive set changed size"

    before_conn, before_config = make_engine("L2")
    after_conn, after_config = make_engine("L3")
    try:
        before = [governed_verdict(before_conn, before_config, c) for c in url_cases]
        after = [governed_verdict(after_conn, after_config, c) for c in url_cases]
    finally:
        before_conn.close()
        after_conn.close()

    assert sum(before) == 0, (
        f"the disclosed baseline is 0/3 and this run says {sum(before)}/3 -- either "
        f"L2 was edited, which destroys the evidence the fix is measured against, or "
        f"the cases changed"
    )
    assert sum(after) == 3, f"ND-040 closes three URL-shaped evasions, got {sum(after)}/3"


def test_the_shell_case_is_still_not_caught() -> None:
    """ND-048, asserted as still open. The fix must not be read as closing more.

    `bash -c "$(echo <base64> | base64 -d)"` carries no matchable literal: the
    governed effect is real and no deterministic parameter rule reaches it. URL
    canonicalization is a different mechanism entirely, and if this ever starts
    passing it must be because someone closed ND-048 on purpose and rewrote the
    disclosure -- not as a side effect.
    """
    _, shell_cases = _evasive_by_shape()
    assert len(shell_cases) == 1
    conn, config = make_engine("L3")
    try:
        assert not governed_verdict(conn, config, shell_cases[0]), (
            "the base64 shell case is being caught -- ND-048 is disclosed as an open "
            "gap with no ticketed fix, so either the disclosure or this test is now "
            "wrong, and neither should be changed by accident"
        )
    finally:
        conn.close()


def test_the_innocents_column_did_not_move() -> None:
    """The over-blocking guard. The opaque-host class is what could break it."""
    assert _score("L2")["innocent"] == "3/3"
    assert _score("L3")["innocent"] == "3/3", (
        "ND-040 governed an innocent host -- over-blocking, and precisely the "
        "failure the opaque class was constrained to avoid (R025)"
    )


@pytest.mark.parametrize("kind", ["named_alias", "generic_covered"])
def test_what_already_worked_still_works(kind: str) -> None:
    """No regression in the coverage L1 and L2 already had."""
    assert _score("L2")[kind] == _score("L3")[kind]


def test_the_disclosed_baseline_layer_is_untouched() -> None:
    """L2 must still score exactly what the disclosure says it scores."""
    assert _score("L2") == {
        "named_alias": "5/5",
        "generic_covered": "4/4",
        "generic_evasive": "0/4",
        "innocent": "3/3",
    }


def test_the_new_layer_scores_what_the_disclosure_will_claim() -> None:
    """The whole L3 row, so a README number and the code cannot drift apart."""
    assert _score("L3") == {
        "named_alias": "5/5",
        "generic_covered": "4/4",
        "generic_evasive": "3/4",
        "innocent": "3/3",
    }
