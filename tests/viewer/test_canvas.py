"""The canvas skin, and the two-zone colour rule (ND-052 / S3-T6).

**State colours are verdicts' alone**, and a policy diff is not a verdict. This suite
holds that boundary the way `test_tokens.py` holds its two — by checking the emitted
artifact rather than by trusting the stylesheet's comments.

Two directions, because a rule checked in one direction is half a rule: the diff zone
must not reach for the semantic pair, **and** the verdict zone must still use it — a
"fix" that stripped `--ok`/`--bad` from the whole page would satisfy a one-sided test
and would have thrown away the signal the rule exists to protect.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import canvas as canvas_model
from onedoor.studio import store as studio_store
from onedoor.studio import validate
from onedoor.viewer import canvas
from tests.conftest import FROZEN_NOW, make_request

SECTION = re.compile(r"<section class='([^']+)'>(.*?)</section>", re.S)


@pytest.fixture
def studio(tmp_path: Path) -> Connection:
    conn = studio_store.open_store(tmp_path / "studio.db")
    yield conn
    conn.close()


def _policy(action: str = "demo.spend", cap: str = "500") -> Policy:
    return Policy(
        action_type=action,
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.restore",
        caps=Caps(eur_day=Decimal(cap)),
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False, required=["amount_eur"]),
    )


def _view(
    conn: Connection, studio: Connection, config: EngineConfig, *, with_backtest: bool = False
) -> canvas_model.CanvasView:
    draft = canvas_model.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    studio_store.save(
        studio, draft.draft_id, policies=[*draft.policies, _policy("demo.new")], now=FROZEN_NOW
    )
    return canvas_model.build(
        conn, studio, draft.draft_id, config=config, with_backtest=with_backtest
    )


def _zones(html: str) -> dict[str, str]:
    """Every `<section>`'s markup, keyed by its leading zone class."""
    found: dict[str, str] = {}
    for classes, body in SECTION.findall(html):
        zone = classes.split()[0]
        found[zone] = found.get(zone, "") + body
    return found


# --- The rule, in both directions -------------------------------------------------


def test_the_diff_zones_markup_carries_no_inline_state_colour(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """One of the rule's two halves: no `style="color:var(--ok)"` in the diff zone.

    **This half only sees the markup.** A violation written into the STYLESHEET —
    `.change.added{border-left-color:var(--ok)}`, which is the likelier mistake — is
    invisible here and is caught by `test_the_verdict_zone_still_uses_them`, which
    requires every rule using the pair to be scoped under the verdict zone. Verified by
    sabotage rather than assumed: colouring an addition green fails that test and not
    this one, which is why this test's name says *markup* rather than claiming the whole
    rule.
    """
    html = canvas.render_page(_view(conn, studio, config), drafts=[])
    diff_markup = _zones(html)[canvas.DIFF_ZONE]
    assert diff_markup, "no diff-zone section was rendered; the test would pass vacuously"
    for var in canvas.STATE_COLOUR_VARS:
        assert var not in diff_markup, f"the diff zone used {var}, which belongs to verdicts"


def test_the_verdict_zone_still_uses_them(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """The other direction: stripping the pair from the whole page is not a fix.

    The backtest panel's counts ARE verdicts — allowed, sent to approval, denied — and
    the semantic pair is exactly right there. A one-sided rule would let a "cleanup"
    throw away the signal the rule protects.
    """
    with tx(conn):
        chain.enable(conn)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("10")}, cost_eur=Decimal("10")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    html = canvas.render_page(_view(conn, studio, config, with_backtest=True), drafts=[])
    styles = html.split("<style>")[1].split("</style>")[0]
    verdict_rules = [
        rule
        for rule in styles.split("}")
        if any(var in rule for var in ("var(--ok)", "var(--bad)"))
    ]
    assert verdict_rules, "no rule uses the semantic pair at all — the signal was thrown away"
    for rule in verdict_rules:
        assert f".{canvas.VERDICT_ZONE}" in rule, (
            f"a state colour is used outside the verdict zone: {rule.strip()!r}"
        )


def test_the_zone_class_is_one_fact_not_two(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """The stylesheet's selector and the markup's class are interpolated from one constant.

    R045 §1 again: two names for one fact drift together, and a test asserting their
    equality certifies the drift. So the CSS is written with a placeholder and the
    constant is substituted at render time — this test proves the placeholder is gone,
    which is the only way the substitution can be observed from outside.
    """
    html = canvas.render_page(_view(conn, studio, config), drafts=[])
    assert "__VERDICT__" not in html, "the zone placeholder reached the page unsubstituted"
    assert f".{canvas.VERDICT_ZONE} " in html


# --- What every canvas must say ---------------------------------------------------


def test_the_moved_state_names_both_hashes_on_the_page(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """R047 §3, at the surface: a warning that names no versions is a mood, not a fact."""
    draft = canvas_model.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    was = draft.base_version
    policy_loader.upsert(conn, _policy(cap="9999"))
    active = policy_loader.current_version(conn)

    view = canvas_model.build(conn, studio, draft.draft_id, config=config)
    html = canvas.render_page(view, drafts=[])
    assert was is not None and active is not None
    assert was in html and active in html
    assert "moved beneath this draft" in html


def test_a_stale_canvas_shows_no_number_from_the_old_base(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """They go stale together, so the page has no panel to render at all."""
    draft = canvas_model.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    policy_loader.upsert(conn, _policy(cap="9999"))
    view = canvas_model.build(conn, studio, draft.draft_id, config=config)
    html = canvas.render_page(view, drafts=[])

    assert "Re-pin this draft" in html
    assert "would become" not in html, "a preview from a dead base survived onto the page"


def test_the_incompleteness_notice_renders_even_with_an_empty_list(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """ "No problems found" and "nothing is wrong" are different claims."""
    view = _view(conn, studio, config)
    assert view.problems == []
    html = canvas.render_page(view, drafts=[])
    assert validate.FOUND_WORDING in html
    assert "not all problems" in html


def test_the_page_escapes_operator_authored_policy_text(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """Policy text reaches this page verbatim, and a security product's GUI is not an XSS hole."""
    draft = canvas_model.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    studio_store.save(
        studio,
        draft.draft_id,
        policies=[_policy("<script>alert(1)</script>")],
        now=FROZEN_NOW,
        title="<img src=x onerror=1>",
    )
    view = canvas_model.build(conn, studio, draft.draft_id, config=config)
    html = canvas.render_page(view, drafts=studio_store.listing(studio))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x onerror=1>" not in html


def test_the_page_raises_rather_than_rendering_a_stale_palette(
    conn: Connection, studio: Connection, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X-6's shape: the design system is a hard requirement of this surface.

    `tokens.css_block` raises when the vendored spec is missing or has drifted, and this
    page does not catch it. A canvas that silently used last week's palette is the same
    failure as an instrument that drifts quietly.
    """
    from onedoor.viewer import tokens

    def boom() -> str:
        raise tokens.TokenError("the spec's token block has changed")

    monkeypatch.setattr(tokens, "root_css", boom)
    monkeypatch.setattr(canvas, "root_css", boom)
    with pytest.raises(tokens.TokenError):
        canvas.render_page(_view(conn, studio, config), drafts=[])
