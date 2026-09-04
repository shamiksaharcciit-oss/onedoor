"""V3 / S4 — the execution ledger: numbered by the chain, filtered honestly, read-only.

The register is the screen an auditor quotes from, so most of what is tested here is
about *what a number on it means*: which ordinal, whose verdict, and what the page does
when it cannot answer.
"""

from __future__ import annotations

import re

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.store.db import Database
from onedoor.studio import history, screens, shell


@pytest.fixture
def ledger(tmp_path):
    database = Database(str(tmp_path / "onedoor.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="reports.read",
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    return conn


def _decide(
    conn, action: str, decision: str, *, version="v1", source="llm", at="2026-08-20T10:00:00Z"
):
    """Write one decision row directly.

    The register is a *read* model; driving the whole engine to produce fixtures would
    test the engine here instead of the page, and would make it hard to produce the
    rows that matter most — the unchained and malformed ones.
    """
    conn.execute(
        "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, created_at, policy_version,"
        " seq) VALUES (?, 'decision', ?, ?, ?, ?, 'bounds', 1, 1, ?, ?, NULL)",
        (
            f"req-{action}-{decision}-{at}",
            action,
            source,
            '{"amount_eur": "40.00"}',
            decision,
            at,
            version,
        ),
    )
    conn.commit()


# --- Numbering -------------------------------------------------------------------------


def test_entries_are_numbered_by_the_chain_and_not_by_the_page(ledger) -> None:
    """**A register's numbers belong to the register.**

    Numbering by position in a filtered listing would invent an ordinal that changes
    when a filter changes, so an auditor quoting "entry 14" would be quoting the page.
    """
    ledger.execute(
        "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, created_at, seq) VALUES"
        " ('a','decision','x.y','llm','{}','executed','passed',1,1,'2026-08-20T10:00:00Z',41),"
        " ('b','decision','x.y','llm','{}','denied','bounds',1,1,'2026-08-20T11:00:00Z',42)"
    )
    ledger.commit()
    entries = history.page(ledger).entries
    assert [e.number for e in entries] == ["#42", "#41"], (
        "the listing renumbered the rows instead of showing the chain's own sequence"
    )


def test_a_row_that_predates_the_chain_says_so_rather_than_showing_zero(ledger) -> None:
    """Absent is a state to render. `0` would be a number the ledger never assigned."""
    _decide(ledger, "reports.read", "executed")
    entry = history.page(ledger).entries[0]
    assert entry.seq is None
    assert entry.number == "unchained"
    assert "unchained" in screens.history_body(history.page(ledger), history.choices(ledger))


# --- Filters ---------------------------------------------------------------------------


def test_each_filter_narrows_by_its_own_column(ledger) -> None:
    _decide(ledger, "reports.read", "executed", version="v1", source="llm")
    _decide(ledger, "payments.transfer", "denied", version="v2", source="ui")

    assert len(history.page(ledger).entries) == 2
    assert len(history.page(ledger, history.Filters(action="reports.read")).entries) == 1
    assert len(history.page(ledger, history.Filters(verdict="denied")).entries) == 1
    assert len(history.page(ledger, history.Filters(version="v2")).entries) == 1
    assert len(history.page(ledger, history.Filters(source="ui")).entries) == 1


def test_filters_compose_rather_than_replace_each_other(ledger) -> None:
    _decide(ledger, "reports.read", "executed", source="llm")
    _decide(ledger, "reports.read", "denied", source="ui")
    both = history.Filters(action="reports.read", verdict="denied")
    assert len(history.page(ledger, both).entries) == 1


def test_a_date_range_bounds_the_register_at_both_ends(ledger) -> None:
    _decide(ledger, "a.b", "executed", at="2026-08-01T00:00:00Z")
    _decide(ledger, "c.d", "executed", at="2026-08-15T00:00:00Z")
    _decide(ledger, "e.f", "executed", at="2026-08-30T00:00:00Z")
    window = history.Filters(since="2026-08-10", until="2026-08-20")
    assert [e.action_type for e in history.page(ledger, window).entries] == ["c.d"]


def test_a_filter_value_reaches_sql_only_as_a_bound_parameter(ledger) -> None:
    """A reader's input is not SQL. The classic shape, asserted rather than assumed."""
    _decide(ledger, "reports.read", "executed")
    hostile = history.Filters(action="' OR 1=1 --")
    assert history.page(ledger, hostile).entries == ()
    assert history.page(ledger).total == 1, "the ledger survived the attempt"


def test_the_filter_choices_come_from_the_ledger_not_the_enum(ledger) -> None:
    """A verdict the engine can produce but this store has never held is not a useful
    filter, and offering it teaches a reader that an empty result means something."""
    _decide(ledger, "reports.read", "executed")
    choices = history.choices(ledger)
    assert choices["verdict"] == ("executed",)
    assert "denied" not in choices["verdict"]


def test_the_missing_api_key_filter_is_stated_on_the_page(ledger) -> None:
    """**The fifth filter R055 V3 asks for cannot be built**: the service authenticates
    with bearer keys and no caller identity is written to the audit row.

    Silently omitting it would read as a filter that exists and found nothing. Absent
    and unverifiable are different, and both are failures to surface.
    """
    html = screens.history_body(history.page(ledger), history.choices(ledger))
    assert history.MISSING_ACTOR_FILTER in html
    assert "does not record one" in html


def test_request_origin_is_not_offered_as_an_identity_filter(ledger) -> None:
    """`source` means *how the request was built*, and the model calls it "informational
    only, never affects the decision". Labelling it "who" would answer a question about
    identity with a fact about provenance."""
    _decide(ledger, "reports.read", "executed")
    html = screens.history_body(history.page(ledger), history.choices(ledger))
    assert "Request origin" in html
    assert not re.search(r"(?i)\b(api key|actor|user)\s*:\s*any", html)


# --- Honesty about size and verdicts ----------------------------------------------------


def test_a_truncated_register_says_how_many_it_did_not_show(ledger) -> None:
    """*No silent caps.* A register that quietly shows the first fifty of nine hundred
    reads as a register with fifty entries."""
    for i in range(history.PAGE_SIZE + 5):
        _decide(ledger, f"a.{i}", "executed")
    page = history.page(ledger)
    assert page.truncated is True
    assert page.total == history.PAGE_SIZE + 5
    assert len(page.entries) == history.PAGE_SIZE
    html = screens.history_body(page, history.choices(ledger))
    assert str(page.total) in html
    assert "most recent" in html


def test_an_untruncated_register_does_not_claim_to_be_truncated(ledger) -> None:
    _decide(ledger, "reports.read", "executed")
    page = history.page(ledger)
    assert page.truncated is False
    assert "most recent" not in screens.history_body(page, history.choices(ledger))


def test_every_verdict_the_engine_can_record_has_a_chip(ledger) -> None:
    """X-14: two lists that must agree are checked, not maintained."""
    from onedoor.guardrail.models import Decision

    assert set(history.DECISION_STATE) == {d.value for d in Decision}


def test_the_chip_carries_the_verdicts_own_word(ledger) -> None:
    """`failed` wears the refusal colour and **is not a refusal**. The word is the
    decision's own, so the colour never stands in for it."""
    _decide(ledger, "reports.read", "failed")
    html = screens.history_body(history.page(ledger), history.choices(ledger))
    assert ">failed<" in html
    assert ">refused<" not in html, "a failure was relabelled as a refusal by its colour"


def test_an_empty_register_distinguishes_no_rows_from_no_matches(ledger) -> None:
    """Two different facts, and an operator's next move differs between them."""
    empty = screens.history_body(history.page(ledger), history.choices(ledger))
    assert "holds no decisions yet" in empty

    _decide(ledger, "reports.read", "executed")
    filtered = screens.history_body(
        history.page(ledger, history.Filters(action="nothing.here")), history.choices(ledger)
    )
    assert "matches those filters" in filtered
    assert "holds no decisions yet" not in filtered


# --- The detail view --------------------------------------------------------------------


def test_the_detail_view_shows_what_r055_asks_for(ledger) -> None:
    """Rule path, params, digests, policy version — each labelled for what it is."""
    _decide(ledger, "reports.read", "denied")
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert "Rule path" in html and "bounds" in html
    assert "amount_eur" in html
    assert "Policy version" in html
    for _column, label, _why in history.DIGEST_LABELS:
        assert label in html


def test_the_digest_labels_say_what_each_digest_actually_covers() -> None:
    """Checked against `guardrail/digests.py`, not guessed from the letter.

    E/I/T/V are evidence, instrument, trust and verdict. A screen that captioned
    `t_digest` as "target" — because the canary pillar uses T that way — would be
    confidently wrong in a compliance product.
    """
    labels = {column: label for column, label, _ in history.DIGEST_LABELS}
    assert labels == {
        "e_digest": "Evidence",
        "i_digest": "Instrument",
        "t_digest": "Trust",
        "v_digest": "Verdict",
    }


# --- R089 F-H1: null digests are not a version statement -------------------------------


def test_null_digests_say_not_recorded_never_no_version_in_force(ledger) -> None:
    """The eight null slots (Digests: Evidence/Instrument/Trust/Verdict; Chain: Previous
    row/This row/Anchor) are content-address fields that are null because ND-017 is
    unimplemented — a legitimate null, but `shell.NOTHING_IN_FORCE` is a sentence about
    a POLICY VERSION, and a version demonstrably is in force on this exact page
    (`policy_version="v1"`, shown under "Policy version"). Fix C's banner bug, reached
    from a second caller of the same function.
    """
    _decide(ledger, "reports.read", "denied", version="v1")
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert shell.NOTHING_IN_FORCE not in html
    assert html.count(shell.NOT_RECORDED) == 7  # 4 digest fields + 3 non-seq chain fields
    assert "v1" in html  # the real version, elsewhere on the same page, unaffected


def test_a_null_sequence_says_unchained_not_not_recorded(ledger) -> None:
    """Sequence is a chain field too, but its null state is a real, named, opt-in state
    (F-S2) — not the ND-017 gap the other three chain fields are null for. It gets the
    word the page's own heading already uses for this row, not the generic label."""
    _decide(ledger, "reports.read", "denied")  # seq is NULL by _decide's own default
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert "<dt>Sequence</dt><dd>unchained</dd>" in html


def test_an_unreported_outcome_is_not_shown_as_nothing_having_happened(ledger) -> None:
    """ND-039/A4b: the PEP's report is a separate vocabulary from the PDP's verdict, and
    absent means *not yet reported* — not *nothing happened*."""
    _decide(ledger, "reports.read", "executed")
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert "not reported" in html


def test_the_detail_view_does_not_claim_to_have_verified_the_chain(ledger) -> None:
    """It renders what was recorded. Re-verification is the Verify page's job, against
    the receipt rather than against this rendering — X-8's discipline in a UI."""
    _decide(ledger, "reports.read", "executed")
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert "does not re-verify" in html
    assert "verified" not in html.replace("re-verify", "")


def test_frozen_params_are_shown_without_normalisation(ledger) -> None:
    """E10: they are the caller's bytes. The page says so, because a reader who assumes
    they were tidied will draw the wrong conclusion from a difference."""
    _decide(ledger, "reports.read", "executed")
    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    html = screens.entry_body(row)
    assert "without normalisation" in html
    assert "40.00" in html, "a decimal string was reformatted on the way to the page"


def test_a_hostile_action_type_cannot_smuggle_markup_into_the_register(ledger) -> None:
    _decide(ledger, "<script>alert(1)</script>", "executed")
    html = screens.history_body(history.page(ledger), history.choices(ledger))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html

    row = history.entry(ledger, history.page(ledger).entries[0].row_id)
    assert "<script>alert(1)</script>" not in screens.entry_body(row)


# --- Read-only ---------------------------------------------------------------------------


def test_the_history_module_contains_no_write(ledger) -> None:
    """R055 V3: *"no mutation of any kind on this screen."*

    Asserted against the source rather than by behaviour, because the property is that
    no write path *exists* — a behavioural test only proves the paths it happened to
    take.
    """
    import inspect

    source = inspect.getsource(history)
    statements = re.findall(r'"\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b', source.upper())
    assert not statements, f"the read model contains a write: {statements}"


def test_the_register_renders_inside_the_shell_and_reaches_nowhere(ledger) -> None:
    _decide(ledger, "reports.read", "executed")
    html = shell.render(
        body=screens.history_body(history.page(ledger), history.choices(ledger)),
        banner=shell.Banner("a" * 64, "2026-08-28", 1, 0),
        active="history",
    )
    assert 'aria-current="page"' in html
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)


def test_a_filter_value_absent_from_the_ledger_is_still_echoed_by_the_form(ledger) -> None:
    """**A form that does not echo what it filtered on is a page lying quietly.**

    Found by the served test: a bookmarked filter whose rows have aged out rendered as
    "any" over an empty register — the control claiming no filter was applied while one
    was, so the emptiness read as "no such decisions ever" instead of "none match".
    """
    _decide(ledger, "reports.read", "executed")
    filters = history.Filters(action="gone.away")
    html = screens.history_body(history.page(ledger, filters), history.choices(ledger))
    assert 'value="gone.away" selected' in html
    assert "not in this ledger" in html
    assert "matches those filters" in html


def test_a_filter_value_present_in_the_ledger_is_not_marked_absent(ledger) -> None:
    """The other direction: the marker must not appear on a value that is there."""
    _decide(ledger, "reports.read", "executed")
    filters = history.Filters(action="reports.read")
    html = screens.history_body(history.page(ledger, filters), history.choices(ledger))
    assert 'value="reports.read" selected' in html
    assert "not in this ledger" not in html
