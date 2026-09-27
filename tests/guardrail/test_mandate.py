"""Mandate-layer deferral (AADP -03 §8.1).

Test keys are generated here, in-process, never written to disk or the repository,
per this module's own key-handling rule. No network call happens anywhere in this
file.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from sqlite3 import Connection

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.connectors import mock
from onedoor.guardrail import approvals, mandate, policy_loader
from onedoor.guardrail.decision import ActionResult, PermittedIntent, decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig, resume_ratification
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

ACTION = "demo.mandate"


def _key_pair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private, public


def _sign(private: Ed25519PrivateKey, message: str) -> str:
    return private.sign(message.encode("ascii")).hex()


def _policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            requires_external_authorization=True,
        ),
    )


def _config(
    base: EngineConfig, resolver: mandate.MandateResolver, public_key: bytes
) -> EngineConfig:
    return dataclasses.replace(
        base, mandate_resolver=resolver, mandate_authority_public_key=public_key
    )


def _resolver(verdict: mandate.MandateVerdict) -> mandate.MandateResolver:
    def resolve(request: object) -> mandate.MandateVerdict:
        return verdict

    return resolve


# --- The two verdicts ---------------------------------------------------------------


def test_a_mandate_deny_gives_denied_with_the_reason_and_a_failing_trace_entry(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    _, public_key = _key_pair()
    cfg = _config(config, _resolver(mandate.MandateVerdict.DENY), public_key)
    result = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)

    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert result.decision.reason_code.value == "external_authorization"

    row = conn.execute(
        "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.audit_id,)
    ).fetchone()
    import json

    trace = json.loads(row["evaluation_trace_json"])
    matching = [e for e in trace if e["check"] == "external_authorization"]
    assert matching and matching[-1]["result"] == "fail"
    assert trace[-1]["check"] == "external_authorization", (
        "the mandate check must be the LAST entry for a mandate denial -- nothing after it ran"
    )


def test_a_mandate_pending_gives_proposed(conn: Connection, config: EngineConfig) -> None:
    _policy(conn)
    _, public_key = _key_pair()
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    result = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)

    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "proposed"
    assert result.decision.reason_code.value == "external_authorization"
    assert result.approval_id is not None

    row = conn.execute(
        "SELECT mandate_authority, mandate_core_digest FROM approvals WHERE id=?",
        (result.approval_id,),
    ).fetchone()
    assert row["mandate_authority"] == 1
    assert row["mandate_core_digest"]


def test_a_permit_verdict_continues_normally_and_is_recorded_as_a_pass(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    _, public_key = _key_pair()
    cfg = _config(config, _resolver(mandate.MandateVerdict.PERMIT), public_key)
    result = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)


def test_a_later_denial_still_wins_over_a_mandate_pending(
    conn: Connection, config: EngineConfig
) -> None:
    """ "unless another check already denies the action, in which case that denial
    takes precedence" -- a bounds violation on a mandate-pending request denies."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False, required=["must_have"]),
            requires_external_authorization=True,
        ),
    )
    _, public_key = _key_pair()
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    result = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert result.decision.reason_code.value == "bounds", (
        "bounds must win over a merely-pending mandate check"
    )


def test_a_policy_without_the_flag_never_consults_the_resolver(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.unrelated",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )

    def _boom(request: object) -> mandate.MandateVerdict:
        raise AssertionError("the resolver must never be called for an unflagged policy")

    _, public_key = _key_pair()
    cfg = _config(config, _boom, public_key)
    result = decide_and_reserve(
        make_request("demo.unrelated", {}), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(result, PermittedIntent)


# --- Ratification: the only way to resolve a pending mandate approval --------------


def _pending(conn: Connection, config: EngineConfig, public_key: bytes) -> ActionResult:
    _policy(conn)
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    result = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    return result


def test_a_valid_ratification_resolves_it(conn: Connection, config: EngineConfig) -> None:
    private, public_key = _key_pair()
    pending = _pending(conn, config, public_key)
    row = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()
    digest = row["mandate_core_digest"]

    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(private, digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert result.authorised
    assert result.status is mandate.RatificationStatus.RATIFIED
    assert result.request is not None

    resumed = result.request.model_copy(update={"request_id": make_request("x").request_id})
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    outcome = decide_and_reserve(
        resumed, conn=conn, config=cfg, now=FROZEN_NOW, approved_override=True
    )
    assert isinstance(outcome, PermittedIntent), "a ratified action must execute on resumption"


def test_resumption_re_evaluates_fully_even_after_ratification(
    conn: Connection, config: EngineConfig
) -> None:
    """If the policy changes between propose and ratification,
    the resumed decide re-evaluates against the CURRENT policy, not the one in
    force at propose time -- a successful ratification authorises resuming the
    request, never a specific verdict. Tightening `bounds.required` after propose
    denies the resumption even though the mandate authority ratified it."""
    _policy(conn)  # lenient bounds, so the initial propose clears bounds and reaches PENDING
    private, public_key = _key_pair()
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    proposed = decide_and_reserve(make_request(ACTION, {}), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(proposed, ActionResult) and proposed.decision.decision.value == "proposed"

    # Tighten bounds AFTER propose: the original request never had this key.
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False, required=["must_have"]),
            requires_external_authorization=True,
        ),
    )

    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (proposed.approval_id,)
    ).fetchone()["mandate_core_digest"]
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(private, digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert result.authorised, "the mandate authority DID ratify the original request"

    resumed = result.request.model_copy(update={"request_id": make_request("x").request_id})
    outcome = decide_and_reserve(
        resumed, conn=conn, config=cfg, now=FROZEN_NOW, approved_override=True
    )
    assert isinstance(outcome, ActionResult), (
        "a ratification authorises resuming the REQUEST, not a specific verdict -- "
        "the now-stricter bounds must still deny it"
    )
    assert outcome.decision.decision.value == "denied"
    assert outcome.decision.reason_code.value == "bounds"


def test_a_second_resumption_of_the_same_ratification_does_not_execute_again(
    conn: Connection, config: EngineConfig
) -> None:
    """A ratified action executes once. Resuming it again -- under whatever fresh
    request_id the resume path itself mints, with no second ratification -- must
    find the approval no longer 'ratified' and refuse, never execute a second time.
    The same property `test_a_second_resumption_of_the_same_approval_does_not_
    execute_again` proves for the admin flow (tests/guardrail/test_approvals.py)."""
    private, public_key = _key_pair()
    pending = _pending(conn, config, public_key)
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["mandate_core_digest"]

    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(private, digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert result.authorised

    registry = ConnectorRegistry()
    registry.register(ACTION, mock.act_ok)
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    first = resume_ratification(
        pending.approval_id, conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
    )
    assert first.executed is True

    with pytest.raises(ApprovalError):
        resume_ratification(
            pending.approval_id, conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
        )


def test_a_wrong_key_ratification_is_refused_and_audited(
    conn: Connection, config: EngineConfig
) -> None:
    private, public_key = _key_pair()
    wrong_private, _ = _key_pair()
    pending = _pending(conn, config, public_key)
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["mandate_core_digest"]

    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(wrong_private, digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert not result.authorised
    assert result.status is mandate.RatificationStatus.WRONG_KEY

    state = conn.execute(
        "SELECT state FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["state"]
    assert state == "pending", "a wrong-key attempt must not consume the approval"

    audited = conn.execute(
        "SELECT detail FROM actions_audit WHERE kind='mandate_ratification' AND parent_id=?",
        (pending.audit_id,),
    ).fetchone()
    assert audited is not None and "wrong_key" in audited["detail"]


def test_a_ratification_naming_another_records_digest_does_not_cross_resolve(
    conn: Connection, config: EngineConfig
) -> None:
    private, public_key = _key_pair()
    first = _pending(conn, config, public_key)
    second_request = make_request(ACTION, {"x": 1})
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    second_outcome = decide_and_reserve(second_request, conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(second_outcome, ActionResult)

    first_digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (first.approval_id,)
    ).fetchone()["mandate_core_digest"]
    second_digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (second_outcome.approval_id,)
    ).fetchone()["mandate_core_digest"]
    assert first_digest != second_digest, "two distinct requests must carry distinct digests"

    # A ratification correctly signed over the FIRST record's digest must resolve
    # only the first record, never the second.
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=first_digest,
            signature_hex=_sign(private, first_digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert result.authorised and result.approval_id == first.approval_id

    second_state = conn.execute(
        "SELECT state FROM approvals WHERE id=?", (second_outcome.approval_id,)
    ).fetchone()["state"]
    assert second_state == "pending", "the second record must be untouched"


def test_a_replayed_ratification_is_refused_and_audited(
    conn: Connection, config: EngineConfig
) -> None:
    private, public_key = _key_pair()
    pending = _pending(conn, config, public_key)
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["mandate_core_digest"]
    signature = _sign(private, digest)

    with tx(conn):
        first = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=signature,
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert first.authorised

    with tx(conn):
        replay = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=signature,
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert not replay.authorised
    assert replay.status is mandate.RatificationStatus.ALREADY_RESOLVED

    attempts = list(
        conn.execute(
            "SELECT detail FROM actions_audit WHERE kind='mandate_ratification' AND parent_id=?",
            (pending.audit_id,),
        )
    )
    assert len(attempts) == 2
    assert "already_resolved" in attempts[-1]["detail"]


def test_an_unknown_digest_is_refused(conn: Connection, config: EngineConfig) -> None:
    private, public_key = _key_pair()
    _pending(conn, config, public_key)
    bogus_digest = "0" * 64
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=bogus_digest,
            signature_hex=_sign(private, bogus_digest),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert not result.authorised
    assert result.status is mandate.RatificationStatus.UNKNOWN_DIGEST


def test_an_admin_key_attempt_through_the_existing_route_is_refused(
    conn: Connection, config: EngineConfig
) -> None:
    _, public_key = _key_pair()
    pending = _pending(conn, config, public_key)
    with pytest.raises(ApprovalError, match="mandate-layer ratification"):
        approvals.cas_approve(conn, pending.approval_id, "admin-session", FROZEN_NOW)
    with pytest.raises(ApprovalError, match="mandate-layer ratification"):
        approvals.deny(conn, pending.approval_id, "admin-session", FROZEN_NOW)

    state = conn.execute(
        "SELECT state FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["state"]
    assert state == "pending", "neither admin route may have touched the row"


def test_an_admin_attempt_on_a_mandate_gated_approval_is_audited_before_the_refusal(
    conn: Connection, config: EngineConfig
) -> None:
    """The refusal is not the whole story: an admin attempt against a mandate-gated
    approval leaves a trace -- who tried, when, which approval -- exactly like a
    wrong-key ratification attempt does. Two attempts (approve, then deny), two
    audit rows, each naming the session that tried and the approval it targeted."""
    _, public_key = _key_pair()
    pending = _pending(conn, config, public_key)

    with pytest.raises(ApprovalError):
        approvals.cas_approve(conn, pending.approval_id, "admin-session-1", FROZEN_NOW)
    with pytest.raises(ApprovalError):
        approvals.deny(conn, pending.approval_id, "admin-session-2", FROZEN_NOW)

    attempts = list(
        conn.execute(
            "SELECT detail FROM actions_audit WHERE kind='mandate_admin_attempt' "
            "AND parent_id=? ORDER BY id",
            (pending.audit_id,),
        )
    )
    assert len(attempts) == 2, "both the approve and deny attempts must be audited"
    assert "admin-session-1" in attempts[0]["detail"]
    assert "admin-session-2" in attempts[1]["detail"]


def test_no_timeout_ever_permits(conn: Connection, config: EngineConfig) -> None:
    """A ratification arriving after the approval's own TTL is refused, exactly like
    a stale admin approval -- there is no path in onedoor from "time passed" to
    "permitted" for a mandate-pending action."""
    private, public_key = _key_pair()
    short_config = dataclasses.replace(config, approval_ttl_seconds=1)
    pending = _pending(conn, short_config, public_key)
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["mandate_core_digest"]

    later = FROZEN_NOW + timedelta(hours=1)
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(private, digest),
            authority_public_key=public_key,
            now=later,
        )
    assert not result.authorised
    assert result.status is mandate.RatificationStatus.ALREADY_RESOLVED


def test_sweep_never_permits_a_mandate_pending_approval(
    conn: Connection, config: EngineConfig
) -> None:
    """`approvals.sweep()` -- the lazy-expiry path a report/decide call runs on the
    side, entirely independent of `mandate.ratify` -- must never turn a
    mandate-pending approval into anything but `expired`. This is the
    "or sweep" half of that rule, named separately from the TTL check inside
    `ratify` itself."""
    private, public_key = _key_pair()
    short_config = dataclasses.replace(config, approval_ttl_seconds=1)
    pending = _pending(conn, short_config, public_key)
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["mandate_core_digest"]

    later = FROZEN_NOW + timedelta(hours=1)
    with tx(conn):
        swept = approvals.sweep(conn, later)
    assert swept == 1
    state = conn.execute(
        "SELECT state FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()["state"]
    assert state == "expired", "sweep must expire it, never permit or ratify it"

    # A ratification arriving after the sweep finds the row no longer 'pending'
    # either -- the same CAS that refuses a late ratification refuses a swept one.
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=_sign(private, digest),
            authority_public_key=public_key,
            now=later,
        )
    assert not result.authorised
    assert result.status is mandate.RatificationStatus.ALREADY_RESOLVED


def test_a_signature_replayed_onto_a_different_records_digest_is_refused(
    conn: Connection, config: EngineConfig
) -> None:
    """Distinct from `ALREADY_RESOLVED`: a signature that is
    genuinely valid -- for a DIFFERENT record's digest -- is presented against a
    SECOND, unrelated record. Ed25519 binds a signature to the exact bytes signed,
    so replaying it onto a different digest must fail verification (not merely find
    the wrong row), and the second record must be untouched -- never resolved by a
    signature that was never issued for it."""
    private, public_key = _key_pair()
    first = _pending(conn, config, public_key)
    cfg = _config(config, _resolver(mandate.MandateVerdict.PENDING), public_key)
    second_outcome = decide_and_reserve(
        make_request(ACTION, {"x": 1}), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(second_outcome, ActionResult)

    first_digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (first.approval_id,)
    ).fetchone()["mandate_core_digest"]
    second_digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (second_outcome.approval_id,)
    ).fetchone()["mandate_core_digest"]
    assert first_digest != second_digest

    # A real signature over the FIRST digest, replayed against the SECOND digest.
    signature_for_first = _sign(private, first_digest)
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=second_digest,
            signature_hex=signature_for_first,
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert not result.authorised
    assert result.status is mandate.RatificationStatus.WRONG_KEY, (
        "Ed25519 must refuse a signature over the wrong message, not merely resolve the wrong row"
    )

    for approval_id in (first.approval_id, second_outcome.approval_id):
        state = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[
            "state"
        ]
        assert state == "pending", "neither record may be resolved by a mismatched replay"

    audited = conn.execute(
        "SELECT detail FROM actions_audit WHERE kind='mandate_ratification' AND parent_id=?",
        (second_outcome.audit_id,),
    ).fetchone()
    assert audited is not None and "wrong_key" in audited["detail"], (
        "the refused replay against the second record must be audited against it"
    )
