"""V4 / S5 — the live room: the arithmetic, the three outcomes, and the switch it cannot throw.

The budget bar is the one number on this product an operator will act on in an incident,
so most of what is tested here is that it means what it says: held money is not spent
money, an undeclared cap is not a full bar, and a control that cannot act is not drawn.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from onedoor.guardrail import killswitch, policy_loader
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.store.db import Database
from onedoor.studio import live, screens, server, shell

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def ledger(tmp_path):
    database = Database(str(tmp_path / "onedoor.db"))
    database.init()
    return database.connect()


@pytest.fixture
def config():
    return server._default_config()


def _capped(conn, action="payments.transfer", **caps):
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action,
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="payments.reverse",
            cost_param="amount_eur",
            caps=Caps(**caps),
            bounds=Bounds(required=["amount_eur"], strict_params=False),
        ),
    )


def _counter(conn, action, kind, key, count, eur):
    conn.execute("INSERT INTO cap_counters VALUES (?,?,?,?,?)", (action, kind, key, count, eur))
    conn.commit()


def _reserve(
    conn,
    action,
    kind,
    eur,
    *,
    created="2026-08-28T11:00:00Z",
    deadline="2026-08-28T11:05:00Z",
    rid=1,
):
    conn.execute(
        "INSERT INTO cap_reservations (intent_audit_id, request_id, deadline_utc,"
        " deltas_json, status, created_utc) VALUES (?,?,?,?, 'held', ?)",
        (rid, f"req-{rid}", deadline, json.dumps([[action, kind, "2026-08-28", 0, eur]]), created),
    )
    conn.commit()


# --- The arithmetic --------------------------------------------------------------------


def test_held_money_is_not_counted_as_spent(ledger, config) -> None:
    """**The defect this page exists to avoid.**

    `caps._reserve_all` bumps `cap_counters` at reserve time, so the counter is
    *consumed plus reserved*. Rendering the counter as "consumed" would show held money
    as money gone — an operator would read a budget as spent while it is still
    reclaimable.
    """
    _capped(ledger, eur_day="2000.00")
    _counter(ledger, "payments.transfer", "eur_day", "2026-08-28", 3, "750.00")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00")

    bar = next(b for b in live.build(ledger, config, NOW).bars if b.kind == "eur_day")
    assert bar.counter == Decimal("750.00")
    assert bar.reserved == Decimal("200.00")
    assert bar.consumed == Decimal("550.00"), "reserved money was double-counted as spend"
    assert bar.free == Decimal("1250.00"), (
        "free must be limit minus the counter, not minus consumed"
    )


def test_consumed_plus_reserved_plus_free_is_the_limit(ledger, config) -> None:
    """The three parts of a bar must account for the whole of it, or the bar is a
    picture rather than a measurement."""
    _capped(ledger, eur_day="2000.00")
    _counter(ledger, "payments.transfer", "eur_day", "2026-08-28", 3, "750.00")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00")
    bar = next(b for b in live.build(ledger, config, NOW).bars if b.kind == "eur_day")
    assert bar.consumed + bar.reserved + bar.free == bar.limit


def test_a_release_between_reads_cannot_show_negative_spend(ledger, config) -> None:
    """A view of a moving store. The clamp says so rather than rendering a negative."""
    _capped(ledger, eur_day="2000.00")
    _counter(ledger, "payments.transfer", "eur_day", "2026-08-28", 1, "100.00")
    _reserve(ledger, "payments.transfer", "eur_day", "300.00")
    bar = next(b for b in live.build(ledger, config, NOW).bars if b.kind == "eur_day")
    assert bar.consumed == Decimal(0)


def test_an_undeclared_cap_draws_no_bar_at_all(ledger, config) -> None:
    """A window with no limit is not a full bar or an empty one — it is **not a bar**.

    Drawing either would state a proportion nobody declared.
    """
    _counter(ledger, "other.thing", "eur_day", "2026-08-28", 1, "55.00")
    bar = next(b for b in live.build(ledger, config, NOW).bars if b.action_type == "other.thing")
    assert bar.unbounded is True
    assert bar.free is None
    assert bar.texts()[2:] == ("unbounded", "none declared")

    html = screens.live_body(live.build(ledger, config, NOW))
    assert "no bar is drawn" in html
    assert "nothing here is a proportion" in html


def test_a_declared_cap_with_no_counter_yet_is_shown_at_zero(ledger, config) -> None:
    """Omitting it would make a fresh deployment look as though it had no budgets."""
    _capped(ledger, eur_day="2000.00", daily_rate=10)
    bars = {b.kind: b for b in live.build(ledger, config, NOW).bars}
    assert set(bars) == {"eur_day", "rate"}
    assert bars["rate"].counter == Decimal(0)
    assert bars["rate"].limit == Decimal(10)


def test_limits_come_from_the_pinned_version_not_the_live_tables(ledger, config) -> None:
    """R058 §1's law applied here: the caps a bar is measured against must come from the
    snapshot the header's digest names, or the page draws a limit the engine is not
    enforcing."""
    _capped(ledger, eur_day="2000.00")
    _counter(ledger, "payments.transfer", "eur_day", "2026-08-28", 1, "10.00")
    ledger.execute(
        "UPDATE policies SET caps_json = ? WHERE action_type = 'payments.transfer'",
        ('{"eur_day": "999999.00"}',),
    )
    ledger.commit()
    bar = next(b for b in live.build(ledger, config, NOW).bars if b.kind == "eur_day")
    assert bar.limit == Decimal("2000.00"), "the bar used an unsnapshotted table write"


def test_no_budget_number_travels_through_a_float(ledger, config) -> None:
    """E006/E8: money is decimal, exactly. A float here would round a budget."""
    _capped(ledger, eur_day="0.30")
    _counter(ledger, "payments.transfer", "eur_day", "2026-08-28", 2, "0.10")
    _reserve(ledger, "payments.transfer", "eur_day", "0.20")
    bar = next(b for b in live.build(ledger, config, NOW).bars if b.kind == "eur_day")
    assert isinstance(bar.consumed, Decimal)
    assert bar.free == Decimal("0.20")
    assert "0.30000000000000004" not in screens.live_body(live.build(ledger, config, NOW))


# --- Reservations ----------------------------------------------------------------------


def test_an_overdue_reservation_is_flagged(ledger, config) -> None:
    """Past its deadline and still held means reclamation has not run — a real state an
    operator needs to see, not a rendering artefact."""
    _capped(ledger, eur_day="2000.00")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00", deadline="2026-08-28T11:05:00Z")
    model = live.build(ledger, config, NOW)
    assert model.reservations[0].overdue(NOW) is True
    assert "past deadline" in screens.live_body(model)


def test_a_reservation_inside_its_deadline_is_not_flagged(ledger, config) -> None:
    _capped(ledger, eur_day="2000.00")
    later = (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00", deadline=later)
    model = live.build(ledger, config, NOW)
    assert model.reservations[0].overdue(NOW) is False
    assert "past deadline" not in screens.live_body(model)


def test_an_unreadable_deadline_is_neither_fine_nor_overdue(ledger, config) -> None:
    """Three outcomes. **Unparseable is not "within deadline"** — a screen must not
    answer a question it could not evaluate."""
    _capped(ledger, eur_day="2000.00")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00", deadline="not a date")
    model = live.build(ledger, config, NOW)
    assert model.reservations[0].overdue(NOW) is None
    assert "deadline unreadable" in screens.live_body(model)


def test_only_held_reservations_are_shown(ledger, config) -> None:
    """Settled, released and expired ones are history, and this is the live room."""
    _capped(ledger, eur_day="2000.00")
    _reserve(ledger, "payments.transfer", "eur_day", "200.00", rid=1)
    ledger.execute(
        "INSERT INTO cap_reservations (intent_audit_id, request_id, deadline_utc,"
        " deltas_json, status, created_utc) VALUES (2,'req-2','x','[]','settled','y')"
    )
    ledger.commit()
    assert len(live.build(ledger, config, NOW).reservations) == 1


# --- The kill switch --------------------------------------------------------------------


def test_the_switch_state_is_shown_with_its_rank_in_words(ledger, config) -> None:
    """R055 V4: *"its rank stated plainly"*, checked against `decision.py` where the
    switch is step 1 and the clamp is unconditional."""
    html = screens.live_body(live.build(ledger, config, NOW))
    assert live.RANK in html
    assert "outranks everything" in html
    assert "including granted approvals" in html


def test_the_page_says_what_the_switch_does_not_stop(ledger, config) -> None:
    """The counterintuitive half. An operator who reads ENGAGED and assumes ratification
    is blocked has the wrong model of their own incident."""
    html = screens.live_body(live.build(ledger, config, NOW))
    assert live.DOES_NOT_STOP in html
    assert "does not stop policy-making" in html


def test_an_engaged_switch_reads_as_engaged_with_its_episode(ledger, config) -> None:
    killswitch.set_engaged(ledger, True, origin="operator")
    model = live.build(ledger, config, NOW)
    assert model.engaged is True
    assert model.engaged_since
    html = screens.live_body(model)
    assert ">engaged<" in html


def test_no_control_is_rendered_for_the_switch(ledger, config) -> None:
    """**R059 §5: a control that renders as operable and is not would be the right-typed
    lie as a button.**

    An admin API exists — `POST /v1/killswitch` on the PDP — and it is not one the Studio
    may use: reaching it needs either a second write path into the enforcer's database
    (R047 §2) or the PDP's admin credential inside a policy editor (R047 §1).
    """
    html = screens.live_body(live.build(ledger, config, NOW))
    assert "<button" not in html
    assert "<form" not in html
    assert 'type="submit"' not in html
    from html import escape

    # Compared escaped: the constant carries apostrophes and the page escapes them,
    # which is the page being correct. Asserting the raw form would have made a
    # correctly-escaped page look like a missing sentence.
    assert escape(live.NO_CONTROL) in html
    assert "cannot engage or release" in html


def test_the_live_module_contains_no_write(ledger) -> None:
    """The same structural fence the register carries. R055 V4 is a read-only screen,
    and the property is that no write path *exists*."""
    import inspect

    source = inspect.getsource(live)
    statements = re.findall(r'"\s*(INSERT|UPDATE|DELETE|DROP|ALTER)\b', source.upper())
    assert not statements, f"the live read model contains a write: {statements}"


def test_reading_the_page_does_not_change_the_switch(ledger, config) -> None:
    """Behaviour beside the fence, as R059 §1 asks: structural assertion as the fence,
    behaviour as the smoke."""
    killswitch.set_engaged(ledger, True, origin="operator")
    before = killswitch.is_engaged(ledger)
    screens.live_body(live.build(ledger, config, NOW))
    screens.live_body(live.build(ledger, config, NOW))
    assert killswitch.is_engaged(ledger) is before is True


# --- Empty states, designed rather than blank ---------------------------------------------


def test_every_list_has_a_designed_empty_state(ledger, config) -> None:
    """R055 V4: *"every list has a designed empty state"* — absent is a state to render."""
    html = screens.live_body(live.build(ledger, config, NOW))
    assert "Nothing is being metered" in html
    assert "Nothing is held" in html
    assert "ever needed a human decision" in html
    assert '<div class="empty">' in html


def test_approval_lifecycles_are_listed_with_their_states(ledger, config) -> None:
    ledger.execute(
        "INSERT INTO approvals (request_json, action_type, state, created_at, expires_at)"
        " VALUES ('{}', 'payments.transfer', 'pending', '2026-08-28T10:00:00Z',"
        " '2026-08-28T11:00:00Z')"
    )
    ledger.commit()
    html = screens.live_body(live.build(ledger, config, NOW))
    assert "payments.transfer" in html
    assert ">pending<" in html


def test_the_page_says_its_numbers_are_a_moment(ledger, config) -> None:
    """A live room that does not say when it was read invites the reader to treat it as
    still true an hour later."""
    assert "as of the moment the page was built" in screens.live_body(
        live.build(ledger, config, NOW)
    )


def test_a_hostile_action_type_cannot_smuggle_markup_into_the_live_room(ledger, config) -> None:
    _counter(ledger, "<script>alert(1)</script>", "eur_day", "2026-08-28", 1, "1.00")
    html = screens.live_body(live.build(ledger, config, NOW))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_live_room_renders_inside_the_shell_and_reaches_nowhere(ledger, config) -> None:
    html = shell.render(
        body=screens.live_body(live.build(ledger, config, NOW)),
        banner=shell.Banner("a" * 64, "2026-08-28", 1, 0),
        active="state",
    )
    assert 'aria-current="page"' in html
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)
