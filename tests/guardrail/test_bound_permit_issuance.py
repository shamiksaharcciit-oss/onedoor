"""Bound permit issuance (bound-permit profile §§3-4), wired into decide_and_reserve.

A policy that asks for a bound permit either gets one -- verifiable end to end by
`onedoor.permit.recipient`, using only that standalone package -- or the action is
denied before any caps are reserved, never permitted without one.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC
from sqlite3 import Connection

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import (
    ActionResult,
    PermittedIntent,
    decide_and_reserve,
    report_result,
)
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Outcome, Policy, Source, Tier
from onedoor.permit import httpsig, jwk, jws
from onedoor.permit.models import PAYMENTS_TRANSFER_V1, REGISTRY, IssuerTableEntry
from onedoor.permit.recipient import InMemoryConsumeStore, RecipientRequest, verify
from tests.conftest import FROZEN_NOW, make_request

ACTION = PAYMENTS_TRANSFER_V1.name
AUDIENCE = "https://payments.example.com/audience"
ISSUER = "https://onedoor.example/issuer"


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private, public


def _policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            present_bound=AUDIENCE,
            bound_permit_action_type=ACTION,
        ),
    )


def _config_with_issuer(base: EngineConfig, issuer_priv: Ed25519PrivateKey) -> EngineConfig:
    return dataclasses.replace(
        base,
        permit_issuer=ISSUER,
        permit_issuer_key_id="k1",
        permit_issuer_private_key=issuer_priv,
    )


_DEFAULT_PARAMS = {"amount": {"currency": "EUR", "max": "40.00"}}


def _request(presenter_key_thumbprint: str | None, params: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    return make_request(
        ACTION, params or dict(_DEFAULT_PARAMS), source=Source.LLM, now=FROZEN_NOW
    ).model_copy(
        update={
            "presented_audience": AUDIENCE,
            "presenter_key_thumbprint": presenter_key_thumbprint,
        }
    )


def test_a_permitted_action_with_a_configured_issuer_gets_a_bound_permit(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    issuer_priv, issuer_pub = _keypair()
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    result = decide_and_reserve(_request(jkt), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is not None

    header, claims, signing_input, signature = jws.parse(result.bound_permit)
    assert header["typ"] == "aadp-permit+jwt"
    assert claims["iss"] == ISSUER
    assert claims["aud"] == AUDIENCE
    assert claims["cnf"] == {"jkt": jkt}


def test_the_issued_permit_verifies_end_to_end_through_the_standalone_recipient_check(
    conn: Connection, config: EngineConfig
) -> None:
    """The issuer side (onedoor.guardrail.bound_permit, via decide_and_reserve) and
    the recipient side (onedoor.permit.recipient) are two independent packages;
    this is the only test that exercises both across the boundary they define."""
    _policy(conn)
    issuer_priv, issuer_pub = _keypair()
    presenter_priv, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    action_params = dict(_DEFAULT_PARAMS)
    result = decide_and_reserve(_request(jkt, action_params), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is not None

    body = b'{"executed":true}'
    import base64
    import hashlib

    _, permit_claims, _, _ = jws.parse(result.bound_permit)
    idempotency_key = httpsig._sf_string(
        str(permit_claims["jti"])
    )  # -00 §12: Idempotency-Key = jti

    content_digest = (
        "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii") + ":"
    )
    components = {
        "@method": "POST",
        "@authority": "recipient.example",
        "@path": "/act",
        "@query": "",
        "content-digest": content_digest,
        "idempotency-key": idempotency_key,
        "aadp-permit": result.bound_permit,
    }
    created = int(FROZEN_NOW.replace(tzinfo=UTC).timestamp())
    sig_input, sig = httpsig.sign(
        components, created=created, keyid=jkt, private_key=presenter_priv
    )

    req = RecipientRequest(
        permit_token=result.bound_permit,
        method="POST",
        authority="recipient.example",
        path="/act",
        query="",
        body=body,
        content_digest_header=content_digest,
        signature_input_header=sig_input,
        signature_header=sig,
        signature_created=created,
        idempotency_key_header=idempotency_key,
        recipient_audience=AUDIENCE,
        action_object=action_params,
    )
    issuer_table = {
        ISSUER: IssuerTableEntry(
            issuer=ISSUER,
            public_key=issuer_pub,
            action_types=frozenset({ACTION}),
            limits={ACTION: {"amount": {"currency": "EUR", "max": "1000.00"}}},
        )
    }
    verification = verify(
        req,
        issuer_table=issuer_table,
        registry=REGISTRY,
        resolve_presenter_key=lambda jkt_: presenter_pub,
        consume_store=InMemoryConsumeStore(),
        now=FROZEN_NOW.replace(tzinfo=UTC),
        local_policy=lambda claims: True,
    )
    assert verification.status.value == "verified", verification.detail


def test_no_issuer_configured_denies_before_caps_are_reserved(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)

    result = decide_and_reserve(_request(jkt), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert result.decision.reason_code.value == "present_bound"
    assert "no issuer is configured" in (result.decision.detail or "")


def test_no_presenter_key_thumbprint_denies_before_caps_are_reserved(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    issuer_priv, _ = _keypair()
    cfg = _config_with_issuer(config, issuer_priv)

    result = decide_and_reserve(_request(None), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert "presenter key thumbprint" in (result.decision.detail or "")


def test_a_policy_with_no_bound_permit_action_type_behaves_exactly_as_before(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.no_permit",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    result = decide_and_reserve(
        make_request("demo.no_permit", {}, source=Source.LLM, now=FROZEN_NOW),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is None


def test_report_result_propagates_the_same_bound_permit_the_intent_carried(
    conn: Connection, config: EngineConfig
) -> None:
    """Every `evaluate_and_execute` caller only ever sees the REPORTED
    ActionResult, never the live PermittedIntent -- the permit must survive
    that collapse, unchanged, or a caller going through the one-call form
    never gets the credential at all.
    """
    _policy(conn)
    issuer_priv, _ = _keypair()
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    intent = decide_and_reserve(_request(jkt), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(intent, PermittedIntent)
    assert intent.bound_permit is not None

    result = report_result(
        intent,
        conn=conn,
        config=cfg,
        outcome=Outcome.SUCCESS,
        payload={},
        error=None,
        now=FROZEN_NOW,
    )
    assert isinstance(result, ActionResult)
    assert result.bound_permit == intent.bound_permit


def test_the_permits_jti_is_minted_independently_of_the_intent_audit_id(
    conn: Connection, config: EngineConfig
) -> None:
    """-00 §3.2: `jti` must not be guessable from, or reducible to, the
    sequential audit row id -- a presenter who can see one permit must not be
    able to derive or enumerate another."""
    _policy(conn)
    issuer_priv, _ = _keypair()
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    result = decide_and_reserve(_request(jkt), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is not None

    _, claims = jws.verify(
        result.bound_permit, issuer_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    jti = claims["jti"]
    audit_id = result.intent_audit_id
    assert jti != str(audit_id)
    assert len(jti) >= 16  # base64url of >=128 random bits is at least this long


def test_the_jti_to_intent_mapping_is_recorded_and_read_back(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    issuer_priv, _ = _keypair()
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    result = decide_and_reserve(_request(jkt), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is not None
    _, claims = jws.verify(
        result.bound_permit, issuer_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )

    row = conn.execute(
        "SELECT permit_jti FROM actions_audit WHERE id=?", (result.intent_audit_id,)
    ).fetchone()
    assert row["permit_jti"] == claims["jti"], (
        "the mapping from jti back to the intent row must be recorded"
    )


def test_an_existing_0_8_x_store_upgrades_and_old_rows_keep_their_digest() -> None:
    """A store that predates migration `0032` has no `permit_jti` column at
    all; upgrading to it must not change the digest of a row that never had
    a bound permit -- the same "a new NULL column reads as absent, not as a
    new fact" discipline every earlier addition to this table follows."""
    from onedoor.decision_digest import decision_digest
    from onedoor.store.db import _MIGRATIONS_DIR, connect, run_migrations

    conn = connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            if path.name >= "0032_permit_jti.sql":
                continue
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (path.name,),
            )
        conn.execute(
            "INSERT INTO actions_audit "
            "(request_id, kind, action_type, source, params_json, decision, reason_code, "
            "nominal_tier, effective_tier, created_at, protocol) "
            "VALUES ('r-1', 'exec_intent', 'demo.legacy', 'ui', '{}', 'executed', 'passed', 1, 1, "
            "'2026-07-05T12:00:00Z', 'aadp/0.2')"
        )
        row_before = dict(
            conn.execute("SELECT * FROM actions_audit WHERE request_id='r-1'").fetchone()
        )
        digest_before = decision_digest(row_before)

        applied = run_migrations(conn)
        assert "0032_permit_jti.sql" in applied

        row_after = dict(
            conn.execute("SELECT * FROM actions_audit WHERE request_id='r-1'").fetchone()
        )
        assert row_after["permit_jti"] is None
        digest_after = decision_digest(row_after)
        assert digest_after == digest_before, (
            "a row with no bound permit must digest identically before and after the upgrade"
        )
    finally:
        conn.close()


def test_sabotage_a_fixed_non_random_jti_is_caught_by_the_length_assertion(
    conn: Connection, config: EngineConfig
) -> None:
    """If minting regressed to something fixed or predictable (not 128 random
    bits), the independence test's own `len(jti) >= 16` bound is what would
    catch the next-smallest version of the same weakness -- a short,
    low-entropy id that happens not to literally equal `str(intent_id)`."""
    import onedoor.guardrail.decision as decision_mod

    _policy(conn)
    issuer_priv, _ = _keypair()
    _, presenter_pub = _keypair()
    jkt = jwk.thumbprint(presenter_pub)
    cfg = _config_with_issuer(config, issuer_priv)

    class _FixedSecrets:
        @staticmethod
        def token_urlsafe(_n: int) -> str:
            return "x"  # SABOTAGE: not random, not 128 bits

    original_secrets = decision_mod.secrets
    decision_mod.secrets = _FixedSecrets()
    try:
        result = decide_and_reserve(_request(jkt), conn=conn, config=cfg, now=FROZEN_NOW)
    finally:
        decision_mod.secrets = original_secrets
    assert isinstance(result, PermittedIntent)
    assert result.bound_permit is not None
    _, claims = jws.verify(
        result.bound_permit, issuer_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    assert claims["jti"] == "x"
    assert len(claims["jti"]) < 16, (
        "the sabotage produced exactly the short, low-entropy id this test checks for"
    )
