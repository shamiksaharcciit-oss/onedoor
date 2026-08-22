"""Render a decision receipt as static HTML (ND-051 / V3).

This module **renders the checker's answer**. It does not check anything: there is no
`hashlib` here, no digest arithmetic, no second opinion about whether a receipt is
sound. `onedoor.guardrail.receipt` decides that, and
`tests/viewer/test_no_second_verification.py` fails if this package ever grows its own
copy. That rule came from the forensics channel, and the reason is simple — two
implementations of "is this valid?" eventually disagree, and the one the user sees is
the one that is wrong.

The law it enforces (spec §2)
-----------------------------
**If verification is not sound, the page shows the failure state; it never shows the
value.** Not the values with a warning banner above them. Not the values greyed out.
A receipt whose evidence did not check out has nothing to display, because every
number on it would be a number this system cannot stand behind — and standing behind
numbers is the entire product.

The absent state is different and is *not* a failure. `row_hash` is NULL in `0.4.1`
because `ND-001` has not run; the page says so, quietly, naming the ticket. A green
tick over a dark column would be exactly the dashboard lie this design exists to
avoid.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from html import escape

from onedoor.guardrail.receipt import (
    CHAIN_COLUMNS,
    Check,
    ReceiptVerification,
    Status,
    hero_decision,
    latest_verdicts,
    verify_decision,
)
from onedoor.viewer.tokens import root_css

SAMPLE_MARKER_KEY = "oneview.sample_store"
"""Written into the store by the demo seeder, read back here.

The label travels **in the store**, never on the command line. A sample page that
loses its "sample" label because someone re-ran the generator without the flag is
exactly what the spec's *"labelled in-frame, always"* is there to stop, and a marker
that lives in the artifact cannot be dropped by a shell history.
"""

_DECISION_WORDS = {
    "denied": ("DENY", "bad"),
    "proposed": ("PROPOSE", "bad"),
    "executed": ("ALLOW", "ok"),
    "dry_run": ("DRY-RUN", "ok"),
    "failed": ("FAILED", "bad"),
}

_REASON_PROSE = {
    "cap_value": "A value cap was reached for this effect: the action would exceed the "
    "declared limit for the window. The reservation was refused; nothing executed.",
    "cap_rate": "A rate cap was reached for this effect: too many of these actions in "
    "the window. The reservation was refused; nothing executed.",
    "malformed": "The request could not be interpreted strictly enough to act on. A "
    "parse differential is a denial, never a bypass.",
    "bounds": "A parameter fell outside the bounds the policy declares, so the action "
    "was denied rather than proposed — nobody is asked to approve an out-of-bounds action.",
    "effect_floor": "An effect label raised the tier floor: this action needs a human, "
    "whichever tool name reached for it.",
    "kill_switch": "The kill switch is engaged.",
    "default_deny": "No policy declares this action, and the engine's default is to refuse.",
    "no_compensating_command": "The action has no registered reversal, so it cannot "
    "execute without a human.",
    "tier_confirm": "The policy places this action at the human-approval tier.",
    "passed": "Every check passed and the action was permitted. Execution is the "
    "caller's obligation, and the result is reported back to this ledger.",
    "observe": "An observe-tier action: recorded, never executed.",
    "dry_run": "A rehearsal. It would have executed; it did not.",
    "expired": "A reservation was reclaimed after its deadline passed unreported.",
}

_STATUS_CLASS = {
    Status.VERIFIED: "ok",
    # Its own class, and deliberately NOT `ok`. A signature that matches the store's own
    # keyring is real information and is not verification -- rendering it green would be
    # the page doing exactly what R038 §1 forbids the system to do: witness itself.
    Status.SELF_CONSISTENT: "partial",
    Status.ABSENT: "absent",
    Status.UNVERIFIABLE: "bad",
    Status.FAILED: "bad",
}


@dataclass(frozen=True)
class PageModel:
    """Everything the template renders, and nothing it computes for itself."""

    hero: sqlite3.Row | None
    verification: ReceiptVerification | None
    tail: list[sqlite3.Row]
    is_sample: bool


def _e(value: object) -> str:
    """Escape for HTML. Every store value passes through here.

    Params are attacker-controlled -- an LLM's arguments reach this table verbatim by
    design (E10) -- so a viewer that interpolates them raw is a stored-XSS hole in a
    security product's demo page.
    """
    return escape("" if value is None else str(value), quote=True)


def build_model(conn: sqlite3.Connection) -> PageModel:
    hero = hero_decision(conn)
    marker = conn.execute("SELECT value FROM config WHERE key=?", (SAMPLE_MARKER_KEY,)).fetchone()
    return PageModel(
        hero=hero,
        verification=None if hero is None else verify_decision(conn, hero),
        tail=latest_verdicts(conn),
        is_sample=marker is not None,
    )


def _verdict_words(row: sqlite3.Row) -> tuple[str, str]:
    return _DECISION_WORDS.get(str(row["decision"]), (str(row["decision"]).upper(), "bad"))


def _params_summary(row: sqlite3.Row) -> str:
    """The frozen params, rendered as the store carries them.

    Not re-serialized, not pretty-printed with different spacing: E10 froze these
    bytes precisely so that what is displayed is what arrived. Sorting the keys for
    display would be this module having an opinion about received data.
    """
    raw = row["params_json"]
    if raw is None:
        return "—"
    text = raw if isinstance(raw, str) else bytes(raw).decode("utf-8", "replace")
    return text


def _budget_cells(row: sqlite3.Row) -> str:
    raw = row["budget_json"]
    if raw is None:
        return ""
    budget = json.loads(raw)
    order = ("dimension", "unit", "window", "limit", "consumed", "remaining")
    cells = []
    for key in order:
        hot = ' class="b-cell hot"' if key == "remaining" else ' class="b-cell"'
        cells.append(
            f"<span{hot}><span class='bk'>{_e(key)}</span>"
            f"<span class='bv'>{_e(budget.get(key))}</span></span>"
        )
    return f"<span class='budget'>{''.join(cells)}</span>"


def _check_rows(verification: ReceiptVerification) -> str:
    out = []
    for check in verification.checks:
        cls = _STATUS_CLASS[check.status]
        out.append(
            f"<div class='c-row'><span class='c-k'>{_e(check.name.replace('_', ' '))}</span>"
            f"<span class='c-v'><span class='vstat {cls}'>{_e(check.status.value)}</span> "
            f"{_e(check.detail)}</span></div>"
        )
    return "".join(out)


def _chain_block(row: sqlite3.Row, chain: Check) -> str:
    """The mockup shows digests here. In `0.4.1` there are none, and it says so.

    Rendering `a3c1e7f0…` from a NULL column would be fabrication, and the spec's own
    law forbids it. What goes here instead is the honest state, naming the ticket that
    will fill it — which is a better demonstration of the product than a fake digest
    would be, because the claim being made is that this system does not show you
    numbers it cannot back.
    """
    if chain.status is Status.ABSENT:
        return (
            "<div class='chain'>"
            "<div class='c-row'><span class='c-k'>Chain</span>"
            f"<span class='c-v absent'>{_e(chain.detail)}</span></div>"
            "</div>"
        )
    rows = "".join(
        f"<div class='c-row'><span class='c-k'>{_e(column)}</span>"
        f"<span class='c-v'>{_e(row[column])}</span></div>"
        for column in CHAIN_COLUMNS
    )
    return f"<div class='chain'>{rows}</div>"


def _failure_card(verification: ReceiptVerification) -> str:
    """What a receipt looks like when its evidence did not check out.

    No fields, no digests, no budget. The values are deliberately absent: showing them
    behind a warning would let a reader copy a number this system cannot stand behind.
    """
    faults = "".join(
        f"<li><b>{_e(c.name.replace('_', ' '))}</b> — {_e(c.status.value)}: {_e(c.detail)}</li>"
        for c in verification.faults
    )
    return f"""<article class="receipt fail">
  <div class="r-head"><div>
    <div class="r-kind">Decision Receipt</div>
    <div class="r-title">This receipt does not verify</div>
  </div></div>
  <div class="verdict bad">
    <span class="badge">NOT SHOWN</span>
    <span class="why">The stored evidence for this decision did not check out, so its
    values are <b>not displayed</b>. A number that cannot be verified is worse than no
    number: it would be read as a fact.</span>
  </div>
  <div class="fields"><ul class="faults">{faults}</ul></div>
  <div class="r-foot"><span class="foot-note">Every check that did not hold is listed
  above. Nothing here is a rendering of the receipt's contents.</span></div>
</article>"""


def _receipt_card(row: sqlite3.Row, verification: ReceiptVerification) -> str:
    word, tone = _verdict_words(row)
    reason = str(row["reason_code"])
    prose = _REASON_PROSE.get(reason, str(row["detail"] or ""))
    budget = _budget_cells(row)
    provenance = verification.by_name("params_provenance")
    budget_row = (
        f"<div class='frow'><span class='fk'>Budget at decision</span>"
        f"<span class='fv'>{budget}</span></div>"
        if budget
        else ""
    )
    resets = ""
    if row["budget_json"] is not None:
        resets = (
            f"<div class='frow'><span class='fk'>Window resets</span>"
            f"<span class='fv'><span class='m'>"
            f"{_e(json.loads(row['budget_json']).get('window_resets_at'))}</span></span></div>"
        )
    return f"""<article class="receipt">
  <div class="r-head">
    <div>
      <div class="r-kind">Decision Receipt</div>
      <div class="r-title">{_e(row["action_type"])} — {_e(row["decision"])}</div>
    </div>
    <div class="r-meta">audit #{_e(row["id"])}<br>{_e(row["created_at"])}<br>
      {_e(row["protocol"] or "aadp/0.1")}</div>
  </div>

  <div class="verdict {tone}">
    <span class="badge">{_e(word)} · {_e(reason)}</span>
    <span class="why">{_e(prose)}</span>
  </div>

  <div class="fields">
    <div class="frow"><span class="fk">Request</span>
      <span class="fv"><span class="m">{_e(row["request_id"])}</span></span></div>
    <div class="frow"><span class="fk">Source</span>
      <span class="fv">{_e(row["source"])}</span></div>
    <div class="frow"><span class="fk">Frozen params</span>
      <span class="fv"><span class="m">{_e(_params_summary(row))}</span></span></div>
    <div class="frow"><span class="fk">Params provenance</span>
      <span class="fv">{_e(provenance.detail)}</span></div>
    <div class="frow"><span class="fk">Tier</span>
      <span class="fv">nominal {_e(row["nominal_tier"])} · effective
        {_e(row["effective_tier"])}</span></div>
    {budget_row}
    {resets}
    <div class="frow"><span class="fk">Policy version</span>
      <span class="fv"><span class="m">{_e(row["policy_version"])}</span></span></div>
  </div>

  {_chain_block(row, verification.by_name("chain"))}

  <div class="chain">{_check_rows(verification)}</div>

  <div class="r-foot">
    <span class="foot-note">Every value above was read from a verified artifact. The
    checks that produced this page are listed with it; re-run
    <span class="m">python -m onedoor.viewer</span> against the same store to
    re-derive them.</span>
  </div>
</article>"""


def _tail(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "<p class='lede'>No verdicts in this store yet.</p>"
    out = []
    for row in rows:
        word, tone = _verdict_words(row)
        out.append(
            f"<div class='t-row {tone}'><span class='t-time'>{_e(row['created_at'])}</span>"
            f"<span class='t-what'><b>{_e(word)}</b> {_e(row['action_type'])} · "
            f"{_e(row['reason_code'])}</span></div>"
        )
    return "".join(out)


def render(model: PageModel) -> str:
    """The whole page. One receipt, one tail, no dashboard (spec §3)."""
    if model.hero is None or model.verification is None:
        body = (
            "<p class='lede'>This store holds no verdicts yet. Run a decision through "
            "the engine and regenerate.</p>"
        )
    elif not model.verification.sound:
        body = _failure_card(model.verification)
    else:
        body = _receipt_card(model.hero, model.verification)

    sample = (
        "<div class='sample'>SAMPLE DATA — this store was generated by "
        "<span class='m'>python -m onedoor.viewer --demo-store</span>. Nothing here "
        "describes a real system.</div>"
        if model.is_sample
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>onedoor — decision receipt</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
{root_css()}
*{{box-sizing:border-box;margin:0}}
html{{background:var(--ground)}}
body{{background:var(--ground);color:var(--ink);font-family:var(--sans);
  line-height:1.5;padding:0 20px 72px;min-height:100vh}}
.shell{{max-width:840px;margin:0 auto}}
header.mast{{display:flex;align-items:baseline;justify-content:space-between;
  padding:30px 2px 22px;border-bottom:1px solid var(--border-soft);margin-bottom:30px}}
.wordmark{{font-weight:700;font-size:17px;letter-spacing:.02em}}
.wordmark span{{color:var(--seal)}}
.mast-note{{font-size:12px;color:var(--faint);letter-spacing:.04em}}
.sample{{border:1px solid var(--seal-dim);color:var(--seal);border-radius:8px;
  padding:10px 14px;margin-bottom:22px;font-size:12.5px;letter-spacing:.03em}}
.lede{{max-width:64ch;color:var(--muted);font-size:14px;margin-bottom:26px}}
.receipt{{background:var(--card);border:1px solid var(--border);border-radius:10px;
  max-width:740px;overflow:hidden;
  box-shadow:0 1px 0 rgba(255,255,255,.03) inset,0 18px 48px -24px rgba(0,0,0,.7)}}
.receipt.fail{{border-color:var(--bad-bd)}}
.r-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
  padding:18px 22px 14px;border-bottom:1px solid var(--border-soft)}}
.r-kind{{font-size:11px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
  color:var(--seal)}}
.r-title{{font-size:19px;font-weight:600;margin-top:3px}}
.r-meta{{text-align:right;font:400 11.5px var(--mono);color:var(--muted);line-height:1.7}}
.verdict{{display:flex;align-items:center;gap:14px;padding:16px 22px;
  border-bottom:1px solid var(--border-soft)}}
.verdict .badge{{font:600 13px var(--mono);letter-spacing:.08em;padding:7px 14px;
  border-radius:6px;border:1px solid;white-space:nowrap}}
.verdict.ok .badge{{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-bd)}}
.verdict.bad .badge{{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-bd)}}
.verdict .why{{font-size:13px;color:var(--muted);max-width:52ch}}
.verdict .why b{{color:var(--ink);font-weight:600}}
.fields{{padding:8px 22px 4px}}
.frow{{display:grid;grid-template-columns:190px 1fr;gap:14px;padding:9px 0;
  border-bottom:1px solid var(--border-soft);align-items:baseline}}
.frow:last-child{{border-bottom:none}}
.fk{{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
  color:var(--faint)}}
.fv{{font-size:13.5px;overflow-wrap:anywhere}}
.fv .m,.m{{font-family:var(--mono);font-size:12.5px;font-variant-numeric:tabular-nums}}
.budget{{display:flex;gap:10px;flex-wrap:wrap;margin-top:2px}}
.b-cell{{background:var(--card-hi);border:1px solid var(--border-soft);border-radius:6px;
  padding:7px 12px;min-width:86px;display:inline-block}}
.b-cell .bk{{font-size:9.5px;font-weight:600;letter-spacing:.1em;color:var(--faint);
  text-transform:uppercase;display:block}}
.b-cell .bv{{font:600 14px var(--mono);margin-top:2px;font-variant-numeric:tabular-nums;
  display:block}}
.b-cell.hot .bv{{color:var(--bad)}}
.chain{{background:var(--surface);border-top:1px solid var(--border-soft);
  padding:14px 22px;display:grid;gap:6px}}
.c-row{{display:grid;grid-template-columns:190px 1fr;gap:14px;align-items:baseline}}
.c-k{{font-size:10.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
  color:var(--faint)}}
.c-v{{font:400 11.5px var(--mono);color:var(--muted);overflow-wrap:anywhere}}
.c-v.absent{{color:var(--faint)}}
.vstat{{font-weight:600;letter-spacing:.06em;text-transform:uppercase}}
.vstat.ok{{color:var(--ok)}}
.vstat.bad{{color:var(--bad)}}
.vstat.absent{{color:var(--faint)}}
.faults{{padding:14px 0 16px 18px;display:grid;gap:8px;font-size:13px;color:var(--muted)}}
.faults b{{color:var(--bad);font-weight:600}}
.r-foot{{display:flex;justify-content:space-between;align-items:center;padding:14px 22px;
  border-top:1px solid var(--border-soft)}}
.foot-note{{font-size:11.5px;color:var(--faint);max-width:56ch}}
.tail{{max-width:740px;margin-top:26px}}
.tail h3{{font-size:11px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);margin-bottom:10px}}
.t-row{{display:flex;gap:14px;align-items:baseline;padding:8px 14px;
  border-left:2px solid var(--border);margin-left:2px;font-size:12.5px}}
.t-row .t-time{{font:400 11px var(--mono);color:var(--faint);white-space:nowrap}}
.t-row .t-what{{color:var(--muted)}}
.t-row .t-what b{{color:var(--ink);font-weight:600}}
.t-row.ok{{border-left-color:var(--ok-bd)}}
.t-row.bad{{border-left-color:var(--bad-bd)}}
@media (max-width:640px){{
  .frow,.c-row{{grid-template-columns:1fr;gap:2px}}
  .r-meta{{text-align:left}}
  .r-head{{flex-direction:column}}
}}
</style>
</head><body>
<div class="shell">
<header class="mast">
  <div class="wordmark">one<span>door</span> · decision receipt</div>
  <div class="mast-note">READ-ONLY · EVERY VALUE FROM A VERIFIED ARTIFACT</div>
</header>
{sample}
<p class="lede">The <b>decision record</b>. An agent asked; the policy layer answered;
this is the account of why, with the checks that back it. Below it, the tail — verdicts
in the order the ledger took them.</p>
{body}
<div class="tail">
  <h3>Tail — verdicts as they landed</h3>
  {_tail(model.tail)}
</div>
</div>
</body></html>
"""


def build_page(conn: sqlite3.Connection) -> str:
    return render(build_model(conn))
