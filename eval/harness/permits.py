"""The permits category runs in-process, through the library
(``decide_and_reserve``/``report_result``), not through the service: the service
has no wire field for a presenter key thumbprint, and adding one would be a
change to ``onedoor/``, which this branch does not make -- logged in
``questions.md``.

Builds one fresh issuer/presenter keypair per run (deterministic within the
run, never persisted) and exercises the real cross-package boundary:
``onedoor.guardrail.decision`` issues, ``onedoor.permit.recipient`` verifies,
exactly as ``tests/guardrail/test_bound_permit_issuance.py`` does.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlite3 import Connection
from zoneinfo import ZoneInfo

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
from onedoor.guardrail.models import ActionRequest, Bounds, Outcome, Policy, Source, Tier
from onedoor.permit import httpsig, jwk
from onedoor.permit.models import PAYMENTS_TRANSFER_V1, IssuerTableEntry
from onedoor.permit.recipient import InMemoryConsumeStore, RecipientRequest, verify
from onedoor.store.db import Database

ACTION = PAYMENTS_TRANSFER_V1.name  # "payments.transfer/1" -- the one registered type
AUDIENCE = "https://recipient.example/audience"
WRONG_AUDIENCE = "https://attacker.example/audience"
ISSUER = "https://eval.onedoor.example/issuer"
_DEFAULT_PARAMS = {"amount": {"currency": "EUR", "max": "40.00"}}


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private, public


@dataclass
class PermitRun:
    db_path: str
    conn: Connection
    config: EngineConfig
    issuer_priv: Ed25519PrivateKey
    issuer_pub: bytes
    presenter_priv: Ed25519PrivateKey
    presenter_pub: bytes
    consume_store: InMemoryConsumeStore
    _prior_permit: str | None = None


def start(db_path: str, *, now: datetime) -> PermitRun:
    db = Database(db_path)
    db.init()
    conn = db.connect()
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
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.restore",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command=ACTION,
            bounds=Bounds(strict_params=False),
        ),
    )
    issuer_priv, issuer_pub = _keypair()
    presenter_priv, presenter_pub = _keypair()
    base = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
    )
    config = dataclasses.replace(
        base,
        permit_issuer=ISSUER,
        permit_issuer_key_id="eval-k1",
        permit_issuer_private_key=issuer_priv,
    )
    return PermitRun(
        db_path=db_path,
        conn=conn,
        config=config,
        issuer_priv=issuer_priv,
        issuer_pub=issuer_pub,
        presenter_priv=presenter_priv,
        presenter_pub=presenter_pub,
        consume_store=InMemoryConsumeStore(),
    )


def propose_and_issue(
    run: PermitRun, *, request_id, now: datetime
) -> PermittedIntent | ActionResult:
    jkt = jwk.thumbprint(run.presenter_pub)
    request = ActionRequest(
        request_id=request_id,  # type: ignore[arg-type]
        action_type=ACTION,
        params=dict(_DEFAULT_PARAMS),
        source=Source.LLM,
        rationale="eval scenario",
        created_at=now,
        presented_audience=AUDIENCE,
        presenter_key_thumbprint=jkt,
    )
    outcome = decide_and_reserve(request, conn=run.conn, config=run.config, now=now)
    if isinstance(outcome, PermittedIntent):
        report_result(
            outcome,
            conn=run.conn,
            config=run.config,
            outcome=Outcome.SUCCESS,
            payload={},
            error=None,
            now=now,
        )
        run._prior_permit = outcome.bound_permit
    return outcome


def present(
    run: PermitRun,
    *,
    shape: str,  # "fresh" | "reuse_prior" | "wrong_recipient" | "expired"
    now: datetime,
) -> tuple[bool, str]:
    """Presents a bound permit to the recipient side. Returns (verified, detail).
    "fresh" issues and presents a brand-new permit, consumed once (the
    reservation is completed on success, as the profile's own "consume,
    perform, store the result" sequence requires). "reuse_prior" re-presents
    the already-consumed permit from the last "fresh" call, for a second,
    different instruction -- the single-use violation this category measures.
    "wrong_recipient" presents a fresh permit to a different audience than it
    names. "expired" issues a permit, then verifies it past its own lifetime."""
    if shape == "reuse_prior":
        if run._prior_permit is None:
            raise RuntimeError("reuse_prior with no prior permit issued yet")
        permit = run._prior_permit
        audience = AUDIENCE
        body = b'{"executed":true,"reused":true}'  # a different instruction, same permit
    else:
        outcome = propose_and_issue(run, request_id=_fresh_request_id(), now=now)
        if not isinstance(outcome, PermittedIntent) or outcome.bound_permit is None:
            return False, "no bound permit was issued for this proposal"
        permit = outcome.bound_permit
        audience = WRONG_AUDIENCE if shape == "wrong_recipient" else AUDIENCE
        body = b'{"executed":true}'

    content_digest = (
        "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii") + ":"
    )
    import onedoor.permit.jws as jws

    _, claims, _, _ = jws.parse(permit)
    idempotency_key = httpsig._sf_string(str(claims["jti"]))
    components = {
        "@method": "POST",
        "@authority": "recipient.example",
        "@path": "/act",
        "@query": "",
        "content-digest": content_digest,
        "idempotency-key": idempotency_key,
        "aadp-permit": permit,
    }
    sign_now = now + timedelta(hours=3) if shape == "expired" else now
    created = int(sign_now.replace(tzinfo=UTC).timestamp())
    sig_input, sig = httpsig.sign(
        components,
        created=created,
        keyid=jwk.thumbprint(run.presenter_pub),
        private_key=run.presenter_priv,
    )
    req = RecipientRequest(
        permit_token=permit,
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
        recipient_audience=audience,
        action_object=dict(_DEFAULT_PARAMS),
    )
    issuer_table = {
        ISSUER: IssuerTableEntry(
            issuer=ISSUER,
            public_key=run.issuer_pub,
            action_types=frozenset({ACTION}),
            limits={ACTION: {"amount": {"currency": "EUR", "max": "1000.00"}}},
        )
    }
    verification = verify(
        req,
        issuer_table=issuer_table,
        registry={ACTION: PAYMENTS_TRANSFER_V1},
        resolve_presenter_key=lambda _jkt: run.presenter_pub,
        consume_store=run.consume_store,
        now=sign_now.replace(tzinfo=UTC),
        local_policy=lambda _claims: True,
    )
    verified = verification.status.value == "verified"
    if verified and not verification.repeat:
        from onedoor.permit.recipient import complete_reservation

        complete_reservation(
            run.consume_store,
            ISSUER,
            str(claims["jti"]),
            content_digest=content_digest,
            confirmation_token=None,
        )
    return verified, (verification.detail or verification.status.value)


_counter = 0


def _fresh_request_id():  # -> uuid.UUID
    global _counter
    _counter += 1
    import uuid

    return uuid.uuid5(uuid.NAMESPACE_URL, f"eval-permit-{_counter}")
