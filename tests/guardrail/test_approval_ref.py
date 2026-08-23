"""PEP-driven resumption via `approval_ref` (ND-009).

The tests that carry weight here are not the ones showing a good ref works. They are:

- **every failure mode behaves identically** and differs only in evidence, because a
  caller who can tell `unknown` from `expired` by behaviour has an oracle for whether
  a ref exists;
- **single-use survives a race** — two simultaneous resumptions, exactly one execution;
- **the kill switch still wins** after a valid ref, asserted rather than assumed;
- **`principal_mismatch` is never emitted**, held the way `sender_mismatch` is.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals, killswitch, policy_loader
from onedoor.guardrail.approval_ref import (
    ApprovalRefStatus,
    canonical_params,
    equivalent,
    resolve,
)
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Decision,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database, tx
from tests.conftest import FROZEN_NOW, make_request


def _tier3(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.pay",
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False, numeric={"amount_eur": NumericBound(max=1000)}),
        ),
    )


def _request(**overrides: object) -> ActionRequest:
    base = {
        "action_type": "demo.pay",
        "params": {"amount_eur": Decimal("250"), "to": "acme"},
    }
    base.update(overrides)
    return make_request(str(base["action_type"]), base["params"], source=Source.LLM)  # type: ignore[arg-type]


def _approved(conn: Connection, request: ActionRequest, config: EngineConfig) -> int:
    """Propose, then approve — the state a PEP later presents a ref for."""
    with tx(conn):
        approval_id = approvals.create(conn, request, config.approval_ttl_seconds, FROZEN_NOW)
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    return approval_id


def _present(
    conn: Connection, config: EngineConfig, approval_id: int | None, request: ActionRequest
) -> object:
    """A NEW decide, with a NEW request_id, carrying the ref (§idem)."""
    resumed = request.model_copy(
        update={"request_id": make_request("x").request_id, "approval_ref": approval_id}
    )
    return decide_and_reserve(resumed, conn=conn, config=config, now=FROZEN_NOW)


def _status(conn: Connection) -> str | None:
    row = conn.execute(
        "SELECT approval_ref_status FROM actions_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["approval_ref_status"]


# --- A2: the happy path, and then every unhappy one behaving identically ----------


def test_a_valid_ref_authorises_a_tier3_action(conn: Connection, config: EngineConfig) -> None:
    _tier3(conn)
    request = _request()
    approval_id = _approved(conn, request, config)
    outcome = _present(conn, config, approval_id, request)
    assert isinstance(outcome, PermittedIntent), "an approved action must execute"
    assert _status(conn) == ApprovalRefStatus.HONORED.value


def test_no_ref_is_absent_and_proposes(conn: Connection, config: EngineConfig) -> None:
    _tier3(conn)
    outcome = _present(conn, config, None, _request())
    assert not isinstance(outcome, PermittedIntent)
    assert outcome.decision.decision is Decision.PROPOSED  # type: ignore[union-attr]
    assert _status(conn) == ApprovalRefStatus.ABSENT.value


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("unknown", ApprovalRefStatus.UNKNOWN),
        ("expired", ApprovalRefStatus.EXPIRED),
        ("consumed", ApprovalRefStatus.CONSUMED),
        ("pending", ApprovalRefStatus.UNKNOWN),
        ("action_mismatch", ApprovalRefStatus.ACTION_MISMATCH),
    ],
)
def test_every_bad_ref_behaves_the_same_and_differs_only_in_evidence(
    conn: Connection, config: EngineConfig, case: str, expected: ApprovalRefStatus
) -> None:
    """The security property: behaviour is uniform, evidence is precise.

    A caller who could tell `unknown` from `expired` by the verdict would have an
    oracle for whether a ref exists — so every one of these proposes, exactly as a
    Tier-3 action with no ref does, and the forensic difference lives only in the
    ledger.
    """
    _tier3(conn)
    request = _request()

    if case == "unknown":
        ref: int | None = 9999
    elif case == "expired":
        ref = _approved(conn, request, config)
        with tx(conn):
            conn.execute(
                "UPDATE approvals SET expires_at=? WHERE id=?", ("2020-01-01T00:00:00Z", ref)
            )
    elif case == "consumed":
        ref = _approved(conn, request, config)
        with tx(conn):
            conn.execute("UPDATE approvals SET state='executed' WHERE id=?", (ref,))
    elif case == "pending":
        with tx(conn):
            ref = approvals.create(conn, request, config.approval_ttl_seconds, FROZEN_NOW)
    else:
        ref = _approved(conn, request, config)
        request = _request(params={"amount_eur": Decimal("900"), "to": "acme"})

    outcome = _present(conn, config, ref, request)
    assert not isinstance(outcome, PermittedIntent), f"{case} must not grant"
    assert outcome.decision.decision is Decision.PROPOSED, (  # type: ignore[union-attr]
        f"{case} must re-evaluate on its own merits, exactly as no ref does"
    )
    assert _status(conn) == expected.value


def test_a_bad_ref_never_raises(conn: Connection, config: EngineConfig) -> None:
    """An error path would tell a prober whether the ref existed."""
    _tier3(conn)
    for ref in (0, -1, 999999):
        outcome = _present(conn, config, ref, _request())
        assert not isinstance(outcome, PermittedIntent)


# --- A3: action-equivalence is identity up to spelling ---------------------------


def test_equivalence_ignores_spelling_and_catches_substance() -> None:
    """R035 §3. The canonical renderer draws the line, not a per-field judgment."""
    base = _request()
    assert equivalent(base, base.model_copy(update={"request_id": make_request("x").request_id}))

    # Spelling: key order and decimal scale are erased by the canonical rendering.
    respelled = _request(params={"to": "acme", "amount_eur": Decimal("250.00")})
    assert equivalent(base, respelled), "a re-spelled identical action must pass"

    # Substance: a bigger transfer is a different action.
    bigger = _request(params={"amount_eur": Decimal("900"), "to": "acme"})
    assert not equivalent(base, bigger), (
        "an approval for 250 must not be spendable on 900 — the human saw params"
    )

    # A different action type, same params.
    assert not equivalent(base, base.model_copy(update={"action_type": "demo.other"}))


def test_canonical_params_erase_only_spelling() -> None:
    assert canonical_params({"a": Decimal("250.00"), "b": 1}) == canonical_params(
        {"b": 1, "a": Decimal("250")}
    )
    assert canonical_params({"a": Decimal("250")}) != canonical_params({"a": Decimal("900")})


def test_a_float_in_params_is_refused_rather_than_rendered() -> None:
    """E10 forbids a float on the evaluation path; rendering one would hide the bug."""
    with pytest.raises(TypeError, match="float reached action-equivalence"):
        canonical_params({"a": 1.5})  # type: ignore[dict-item]


# --- A4: single-use, and the race ------------------------------------------------


def test_a_ref_is_single_use(conn: Connection, config: EngineConfig) -> None:
    _tier3(conn)
    request = _request()
    ref = _approved(conn, request, config)
    assert isinstance(_present(conn, config, ref, request), PermittedIntent)

    second = _present(conn, config, ref, request)
    assert not isinstance(second, PermittedIntent), "a ref must not authorise twice"
    assert _status(conn) == ApprovalRefStatus.CONSUMED.value


def test_two_simultaneous_resumptions_yield_exactly_one_execution(tmp_path: Path) -> None:
    """The DoD concurrency test, run against two real connections.

    `BEGIN IMMEDIATE` serialises the two transactions, and the consume is the FIRST
    write inside it with `rowcount` as the gate — so the loser sees `state='executed'`
    and resolves to `consumed`. **A lost race never denies and never errors; it just
    does not grant**, and the action re-evaluates on its own merits.
    """
    from zoneinfo import ZoneInfo

    database = Database(str(tmp_path / "race.db"))
    database.init()
    setup = database.connect()
    cfg = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))
    try:
        _tier3(setup)
        request = _request()
        ref = _approved(setup, request, cfg)
    finally:
        setup.close()

    outcomes = []
    conns = [database.connect(), database.connect()]
    try:
        for conn in conns:
            outcomes.append(_present(conn, cfg, ref, request))
    finally:
        for conn in conns:
            conn.close()

    permitted = [o for o in outcomes if isinstance(o, PermittedIntent)]
    assert len(permitted) == 1, f"exactly one execution, got {len(permitted)}"
    loser = next(o for o in outcomes if not isinstance(o, PermittedIntent))
    assert loser.decision.decision is Decision.PROPOSED, (  # type: ignore[union-attr]
        "the loser must re-evaluate on its own merits, not error and not deny"
    )


def test_the_consume_is_the_first_write(conn: Connection, config: EngineConfig) -> None:
    """Read-then-decide-then-mark would let two resumptions through.

    Asserted structurally: after a resolution that authorises, the approval row is
    already `executed` — before any decision row exists.
    """
    _tier3(conn)
    request = _request()
    ref = _approved(conn, request, config)
    with tx(conn):
        resolution = resolve(conn, approval_ref=ref, presented=request, now=FROZEN_NOW)
        assert resolution.authorised
        state = conn.execute("SELECT state FROM approvals WHERE id=?", (ref,)).fetchone()["state"]
    assert state == "executed", "the ref must be consumed before anything else happens"


# --- A6: the kill switch still wins ----------------------------------------------


def test_the_kill_switch_beats_a_valid_ref(conn: Connection, config: EngineConfig) -> None:
    """§invariants #1. A valid ref resumes an approval; it does not overrule a stop.

    Stated as an invariant rather than left to emerge from check ordering — the lesson
    `ND-040`/U4 taught, where a protection that depended on a second declaration turned
    out to be a default.
    """
    _tier3(conn)
    request = _request()
    ref = _approved(conn, request, config)
    with tx(conn):
        killswitch.set_engaged(conn, True)

    outcome = _present(conn, config, ref, request)
    assert not isinstance(outcome, PermittedIntent), "the kill switch must win"
    assert outcome.decision.decision is Decision.DENIED  # type: ignore[union-attr]
    assert outcome.decision.reason_code.value == "kill_switch"  # type: ignore[union-attr]
    assert _status(conn) == ApprovalRefStatus.HONORED.value, (
        "the ref WAS honored; the kill switch is a separate stop, and the evidence "
        "must show both facts rather than blaming the approval"
    )


# --- Q2: the reserved status ------------------------------------------------------


def test_principal_mismatch_is_reserved_and_never_emitted() -> None:
    """R035 §2. A status for a check that cannot hold is a gate that never fired.

    onedoor has no authenticated per-caller identity: `session_id` is caller-supplied
    and arrives in the same untrusted body as the ref. Scoping to it would be a control
    that does not control anything. The value exists so the evidence vocabulary is
    complete in one increment; it starts being emitted when `ND-004`/`ND-005` provide
    an identity the engine can check.

    Held exactly as `sender_mismatch` is held in the reason-code vocabulary — by a test
    that greps the engine, so adding an emission site fails CI rather than review.
    """
    package = Path(__file__).resolve().parents[2] / "onedoor"
    emitters = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "PRINCIPAL_MISMATCH" not in text:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if "PRINCIPAL_MISMATCH" in stripped and not stripped.startswith(
                ("#", '"', "PRINCIPAL")
            ):
                emitters.append(f"{path.name}: {stripped}")
    assert not emitters, (
        f"principal_mismatch is reserved and must never be emitted until an "
        f"authenticated identity exists: {emitters}"
    )
    assert ApprovalRefStatus.PRINCIPAL_MISMATCH.value == "principal_mismatch"


def test_the_evidence_vocabulary_is_the_settled_seven() -> None:
    """`CONFORMANCE.md` §6 fixes the set; the enum is built to it, not beside it."""
    assert {s.value for s in ApprovalRefStatus} == {
        "absent",
        "honored",
        "expired",
        "consumed",
        "unknown",
        "action_mismatch",
        "principal_mismatch",
    }


# --- The evidence lands on the row, and is hashed ---------------------------------


def test_the_status_is_recorded_on_every_decision(conn: Connection, config: EngineConfig) -> None:
    """Absent is written explicitly, not left NULL: a pre-ND-009 row's NULL means the
    field did not exist, which is a different fact from "no ref was presented".

    The version hint is the opposite case, and the contrast is the point. It is stamped
    only where a row is SEALED, so an unchained row carries none — a hint on a row that
    was never sealed would be a claim about a sealing that did not happen. Absent there
    means "not sealed"; absent in `approval_ref_status` would mean "the field did not
    exist". Two NULLs, two different facts, each earned rather than defaulted.
    """
    _tier3(conn)
    _present(conn, config, None, _request())
    row = conn.execute(
        "SELECT approval_ref_status, preimage_version, row_hash FROM actions_audit "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["approval_ref_status"] == "absent"
    assert row["row_hash"] is None, "the fixture must be an unchained store"
    assert row["preimage_version"] is None, "an unsealed row must not claim a sealing version"


def test_a_sealed_row_carries_the_version_that_sealed_it(
    conn: Connection, config: EngineConfig
) -> None:
    """And the other half: where there IS a seal, the hint names it."""
    from onedoor.guardrail import chain
    from onedoor.guardrail.preimage import CURRENT_VERSION

    _tier3(conn)
    with tx(conn):
        chain.enable(conn)
    _present(conn, config, None, _request())
    row = conn.execute(
        "SELECT preimage_version, row_hash FROM actions_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["row_hash"] is not None
    assert row["preimage_version"] == CURRENT_VERSION


def test_the_status_is_inside_the_hash(conn: Connection, config: EngineConfig) -> None:
    """R035 §1: flipping `expired` to `honored` is the edit a chain exists to catch."""
    from onedoor.guardrail import chain
    from onedoor.guardrail.preimage import row_hash_of

    _tier3(conn)
    with tx(conn):
        chain.enable(conn)
    _present(conn, config, None, _request())
    row = conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()
    assert row_hash_of(row) == row["row_hash"]

    values = {k: row[k] for k in row.keys()}
    values["approval_ref_status"] = "honored"

    class _Fake(dict):  # minimal Row stand-in: keys() plus subscripting
        def keys(self) -> list[str]:  # type: ignore[override]
            return list(super().keys())

    assert row_hash_of(_Fake(values)) != row["row_hash"], (  # type: ignore[arg-type]
        "editing the approval evidence did not change the row hash"
    )


def test_a_resumed_request_keeps_its_received_provenance(
    conn: Connection, config: EngineConfig
) -> None:
    """R034/R035: the E10 label survives the approval hop."""
    _tier3(conn)
    raw = '{"amount_eur": 250, "to": "acme"}'
    request = _request().model_copy(update={"params_raw": raw})
    ref = _approved(conn, request, config)
    resumed = request.model_copy(
        update={"request_id": make_request("x").request_id, "approval_ref": ref, "params_raw": raw}
    )
    outcome = decide_and_reserve(resumed, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(outcome, PermittedIntent)
    row = conn.execute(
        "SELECT params_json, params_provenance FROM actions_audit WHERE id=?",
        (outcome.intent_audit_id,),
    ).fetchone()
    assert row["params_provenance"] == "received"
    assert row["params_json"] == raw


def test_the_frozen_request_survives_the_approval_round_trip(
    conn: Connection, config: EngineConfig
) -> None:
    """Checked before the ticket was decomposed, kept as a regression."""
    request = _request().model_copy(update={"params_raw": '{"a": 1}', "session_id": "sess-7"})
    _tier3(conn)
    ref = _approved(conn, request, config)
    stored = conn.execute("SELECT request_json FROM approvals WHERE id=?", (ref,)).fetchone()
    back = ActionRequest.model_validate(json.loads(stored["request_json"], parse_float=Decimal))
    assert back.params_raw == '{"a": 1}'
    assert back.session_id == "sess-7"
    assert back.params["amount_eur"] == Decimal("250")


def test_resolution_requires_the_callers_transaction(conn: Connection) -> None:
    """A sanity check on the contract: the CAS is only race-free inside one."""
    assert isinstance(conn, sqlite3.Connection)
    result = resolve(conn, approval_ref=None, presented=_request(), now=FROZEN_NOW)
    assert result.status is ApprovalRefStatus.ABSENT
    assert not result.authorised


def test_an_expired_window_is_expired_even_while_state_says_approved(
    conn: Connection, config: EngineConfig
) -> None:
    """Both directions: the state machine and the clock each have a veto."""
    _tier3(conn)
    request = _request()
    ref = _approved(conn, request, config)
    later = FROZEN_NOW + timedelta(days=30)
    with tx(conn):
        result = resolve(conn, approval_ref=ref, presented=request, now=later)
    assert result.status is ApprovalRefStatus.EXPIRED
    assert not result.authorised


def test_a_number_and_its_string_spelling_are_not_equivalent() -> None:
    """The trap the number tag exists for, and it is permissive if you fall in.

    `Decimal("250")` serialises to the JSON integer `250`, and `parse_float` never sees
    an integer — so the stored side of an approval carries `int` where the presented
    side carries `Decimal`. Normalising both through `canon_decimal` fixes that. But
    normalising to a bare *string* would then equate the number `250` with the string
    `"250"`, and the vendored artifact's rule 4 names that trap exactly: *int and
    "int-string" are distinct bytes*.

    It matters here more than usual: the bounds gate that would refuse a string amount
    never runs, because the ref already granted.
    """
    assert canonical_params({"a": Decimal("250")}) != canonical_params({"a": "250"})
    assert canonical_params({"a": 250}) == canonical_params({"a": Decimal("250.00")})
    assert canonical_params({"a": True}) != canonical_params({"a": 1}), (
        "True is not the number 1, and bool subclasses int"
    )


def test_equivalence_survives_the_json_round_trip(conn: Connection, config: EngineConfig) -> None:
    """The regression: a whole-number amount must still match after storage.

    Before the number tag, this reported `action_mismatch` for every integral amount —
    safe, because it refused to grant, but wrong.
    """
    _tier3(conn)
    request = _request()
    ref = _approved(conn, request, config)
    stored = ActionRequest.model_validate(
        json.loads(
            conn.execute("SELECT request_json FROM approvals WHERE id=?", (ref,)).fetchone()[
                "request_json"
            ],
            parse_float=Decimal,
        )
    )
    assert isinstance(stored.params["amount_eur"], int), (
        "the fixture must reproduce the int/Decimal asymmetry this guards"
    )
    assert equivalent(stored, request)
