"""Confirmation-format test vectors (`confirmation_vectors_1.json`, draft 1),
re-verified against this repository's own code -- the same promise
`test_vectors.py` makes for the other vector files, extended to cover the
recipient confirmation (bound-permit profile §10, closed by a separate,
not-yet-public format note).

`test_confirmation_vectors_file_reproduces_from_this_repositorys_own_code`
ports the external generator's own algorithm, using this repository's
`onedoor.permit` modules directly rather than pointing at an extracted sdist,
and compares the resulting bytes against the committed file.
`test_confirmation_build_matches_c01_byte_for_byte` goes the other way: given
the shared step's real permit and request, run through this repository's own
`recipient.verify()`, `onedoor.permit.confirmation.build` must produce the
exact token C01 already carries.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization as _ser
from cryptography.hazmat.primitives.asymmetric import ed25519

from onedoor.permit import confirmation, httpsig, jwk, jws
from onedoor.permit.action import action_digest
from onedoor.permit.models import VerificationStatus
from onedoor.permit.recipient import RecipientRequest

VECTORS = Path(__file__).parent
SHA256 = "d3980d8a874bb1a154b81045c7b225550688b4926b947d5eab5fe50e9200d638"


def _load() -> dict:  # type: ignore[type-arg]
    return json.loads((VECTORS / "confirmation_vectors_1.json").read_text(encoding="utf-8"))


def test_confirmation_vectors_file_is_the_accepted_pack_byte_for_byte() -> None:
    data = (VECTORS / "confirmation_vectors_1.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256


# ---------------------------------------------------------------------------
# Regenerate the whole file from this repository's own code, the generator's
# way, and compare bytes.
# ---------------------------------------------------------------------------

K = {
    "issuer": "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
    "presenter": "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
    "recipient": "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
    "other_recipient": "f5e5767cf153319517630f226876b86c8160cc583bc013744c6bf255f5cc0ee5",
}
EXPECT_PUB = {
    "issuer": "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    "presenter": "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
    "recipient": "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
    "other_recipient": "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
}


def _sd(data: bytes) -> str:
    return "sha-256=:" + base64.b64encode(hashlib.sha256(data).digest()).decode("ascii") + ":"


def _rebuild_vectors_file() -> bytes:
    priv = {
        name: ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_))
        for name, hex_ in K.items()
    }
    pub = {}
    for name, key in priv.items():
        raw = key.public_key().public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
        assert raw.hex() == EXPECT_PUB[name], name
        pub[name] = raw
    kid = {name: jwk.thumbprint(pub[name]) for name in K}

    iss, aud = "https://issuer.example", "https://payments.example"
    t0 = 1790000000
    action_object = {"type": "pay", "invoice": "INV-0001", "amount_eur": "40.00"}
    permit = jws.encode(
        {"alg": "EdDSA", "kid": kid["issuer"], "typ": "aadp-permit+jwt"},
        {
            "iss": iss,
            "sub": "agent-1",
            "aud": aud,
            "jti": "p-0001",
            "iat": t0,
            "nbf": t0,
            "exp": t0 + 120,
            "cnf": {"jkt": kid["presenter"]},
            "authorization_details": [
                {"type": "payments.transfer/1", "amount": {"currency": "EUR", "max": "40.00"}}
            ],
            "action_digest": action_digest(action_object),
            "verdict": "permit",
            "currentness": "time-bounded",
            "policy_version": "sha256:" + "0" * 64,
        },
        priv["issuer"],
    )

    body = json.dumps(action_object, separators=(",", ":")).encode()
    comp = {
        "@method": "POST",
        "@authority": "payments.example",
        "@path": "/v1/transfers",
        "@query": "?",
        "content-digest": _sd(body),
        "idempotency-key": '"p-0001"',
        "aadp-permit": permit,
    }
    created = t0 + 5
    base = httpsig.signature_base(comp, created=created, keyid=kid["presenter"])
    sig_input, sig = httpsig.sign(
        comp, created=created, keyid=kid["presenter"], private_key=priv["presenter"]
    )

    def build_confirmation(  # type: ignore[no-untyped-def]
        signer: str = "recipient", typ: str = "aadp-confirmation+jwt", iss: str = aud, **over
    ):
        p: dict[str, object] = {
            "iss": iss,
            "permit": {
                "iss": "https://issuer.example",
                "jti": "p-0001",
                "digest": _sd(permit.encode("ascii")),
            },
            "request": {
                "content_digest": _sd(body),
                "signature_base_digest": _sd(base.encode("ascii")),
            },
            "action_digest": action_digest(action_object),
            "outcome": "effected",
            "recipient_action_id": "TX-0001",
            "iat": t0 + 6,
        }
        for k, v in over.items():
            if v is None:
                p.pop(k, None)
            else:
                p[k] = v
        sign_kid = kid["other_recipient"] if signer == "other_recipient" else kid["recipient"]
        return jws.encode({"alg": "EdDSA", "kid": sign_kid, "typ": typ}, p, priv[signer])

    c_ok = build_confirmation()
    other_permit_digest = _sd(b"some-other-permit")
    vectors = {
        "C01": {"case": "effected, every row passes", "confirmation": c_ok, "expect": "PASS"},
        "C02": {
            "case": "refused at step 9, the step reported its outcome as not ok",
            "confirmation": build_confirmation(
                outcome="refused",
                reason="action-mismatch",
                step=9,
                recipient_action_id=None,
                action_digest=None,
            ),
            "step_outcome": "error",
            "expect": "PASS (refused, not acted)",
        },
        "C03": {
            "case": "refused, but the step reported ok",
            "confirmation": build_confirmation(
                outcome="refused", reason="local-policy", step=12, recipient_action_id=None
            ),
            "step_outcome": "ok",
            "expect": "FAIL outcome row",
        },
        "C04": {
            "case": "signed by the presenter key, not the recipient's",
            "confirmation": build_confirmation(signer="presenter"),
            "expect": "FAIL key row",
        },
        "C05": {
            "case": "recipient not in the trust list",
            "confirmation": c_ok,
            "trust": {},
            "expect": "COULD NOT CHECK key row",
        },
        "C06": {
            "case": "cites another permit",
            "confirmation": build_confirmation(
                permit={"iss": iss, "jti": "p-0001", "digest": other_permit_digest}
            ),
            "expect": "FAIL permit row",
        },
        "C07": {
            "case": "request body digest differs from the recorded request",
            "confirmation": build_confirmation(
                request={
                    "content_digest": _sd(body + b" "),
                    "signature_base_digest": _sd(base.encode()),
                }
            ),
            "expect": "FAIL request row",
        },
        "C08": {
            "case": "action digest differs from the decision's",
            "confirmation": build_confirmation(
                action_digest=action_digest({**action_object, "amount_eur": "400.00"})
            ),
            "expect": "FAIL request row",
        },
        "C09": {
            "case": "second step, same permit, a different effected confirmation",
            "confirmation": c_ok,
            "second": build_confirmation(recipient_action_id="TX-0002", iat=t0 + 9),
            "expect": "FAIL single-use row",
        },
        "C10": {
            "case": "second step, same permit, the byte-identical confirmation (a repeat)",
            "confirmation": c_ok,
            "second": c_ok,
            "expect": "PASS single-use row (repeat)",
        },
        "C11": {
            "case": "typ is the permit's, not a confirmation's",
            "confirmation": build_confirmation(typ="aadp-permit+jwt"),
            "expect": "FAIL key row (malformed)",
        },
        "C12": {
            "case": "effect-unknown, step reported ok",
            "confirmation": build_confirmation(outcome="effect-unknown", recipient_action_id=None),
            "step_outcome": "ok",
            "expect": "FAIL outcome row",
        },
    }

    def bare(**p):  # type: ignore[no-untyped-def]
        return jws.encode(
            {"alg": "EdDSA", "kid": kid["recipient"], "typ": "aadp-confirmation+jwt"},
            {"iss": aud, **p},
            priv["recipient"],
        )

    other = "https://ledger.example"
    vectors.update(
        {
            "C13": {
                "case": "refused at step 1 (malformed): no permit, request or action members",
                "confirmation": bare(outcome="refused", step=1, reason="malformed", iat=t0 + 6),
                "step_outcome": "error",
                "expect": "PASS (refused, not acted); Permit and Request rows not counted for this step",
            },
            "C14": {
                "case": "an unknown payload member",
                "confirmation": build_confirmation(note="x"),
                "expect": "PASS, the Key row's detail names the member",
            },
            "C15": {
                "case": "recipient on the list, its kid not listed",
                "confirmation": c_ok,
                "trust": {aud: [kid["other_recipient"]]},
                "expect": "COULD NOT CHECK key row",
            },
            "C16": {
                "case": "no recipient list given",
                "confirmation": c_ok,
                "trust": None,
                "expect": "COULD NOT CHECK key row",
            },
            "C17": {
                "case": "refused while the first was in progress (step 13), then effected, same permit",
                "confirmation": build_confirmation(
                    outcome="refused",
                    step=13,
                    reason="idempotency-conflict",
                    recipient_action_id=None,
                    iat=t0 + 5,
                ),
                "step_outcome": "error",
                "second": c_ok,
                "expect": "PASS single-use row",
            },
            "C18": {
                "case": "signed by another listed recipient, its iss is not the permit's aud",
                "confirmation": build_confirmation(signer="other_recipient", iss=other),
                "trust": {aud: [kid["recipient"]], other: [kid["other_recipient"]]},
                "expect": "FAIL permit row",
            },
            "C19": {
                "case": "step reported an error, but holds an effected confirmation",
                "confirmation": c_ok,
                "step_outcome": "error",
                "expect": "FAIL outcome row",
            },
            "C20": {
                "case": "step presented the permit and reported ok, no confirmation recorded",
                "confirmation": None,
                "expect": "COULD NOT CHECK outcome row",
            },
            "C21": {
                "case": "confirmation iat an hour after the step ended",
                "confirmation": build_confirmation(iat=t0 + 3600),
                "expect": "FAIL request row (time)",
            },
        }
    )

    out = {
        "format": "confirmation-vectors/1-draft",
        "keys": {
            name: {
                "source": "RFC 8032 section 7.1 TEST " + ["1", "2", "3", "1024"][i],
                "secret_hex": K[name],
                "public_hex": pub[name].hex(),
                "kid": kid[name],
            }
            for i, name in enumerate(K)
        },
        "trust": {aud: [kid["recipient"]]},
        "step": {
            "started": t0 + 4,
            "ended": t0 + 7,
            "permit_aud": aud,
            "permit_exp": t0 + 120,
            "permit": permit,
            "permit_digest": _sd(permit.encode("ascii")),
            "action_object": action_object,
            "action_digest": action_digest(action_object),
            "request": {
                **comp,
                "body": body.decode(),
                "signature-input": sig_input,
                "signature": sig,
            },
            "signature_base": base,
            "content_digest": _sd(body),
            "signature_base_digest": _sd(base.encode("ascii")),
            "outcome": "ok",
        },
        "vectors": vectors,
    }
    return json.dumps(out, indent=1, sort_keys=True).encode("utf-8") + b"\n"


def test_confirmation_vectors_file_reproduces_from_this_repositorys_own_code() -> None:
    committed = (VECTORS / "confirmation_vectors_1.json").read_bytes()
    assert _rebuild_vectors_file() == committed


# ---------------------------------------------------------------------------
# One test per vector, through `confirmation.check` (C09/C10/C17 through the
# single-use helper instead, since they are pairs).
# ---------------------------------------------------------------------------


def _recipients(data: dict, table) -> dict:  # type: ignore[no-untyped-def,type-arg]
    if table is None:
        return {}
    by_kid = {k["kid"]: bytes.fromhex(k["public_hex"]) for k in data["keys"].values()}
    return {iss: {kid: by_kid[kid] for kid in kids} for iss, kids in table.items()}


def _check_vector(data: dict, vector_id: str, *, step_outcome_ok: bool = True):  # type: ignore[no-untyped-def,type-arg]
    v = data["vectors"][vector_id]
    trust = v["trust"] if "trust" in v else data["trust"]
    step = data["step"]
    return confirmation.check(
        v["confirmation"],
        permit_token=step["permit"],
        permit_aud=step["permit_aud"],
        content_digest=step["content_digest"],
        signature_base=step["signature_base"],
        action_digest=step["action_digest"],
        step_started=step["started"],
        step_ended=step["ended"],
        step_outcome_ok=step_outcome_ok,
        recipients=_recipients(data, trust),
    )


def test_c01_effected_every_row_passes() -> None:
    data = _load()
    result = _check_vector(data, "C01")
    assert result.status is VerificationStatus.VERIFIED


def test_c02_refused_at_step_9_no_action_digest_step_error_passes() -> None:
    data = _load()
    result = _check_vector(data, "C02", step_outcome_ok=False)
    assert result.status is VerificationStatus.VERIFIED


def test_c03_refused_at_step_12_step_ok_fails_the_outcome_row() -> None:
    data = _load()
    result = _check_vector(data, "C03", step_outcome_ok=True)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c04_signed_by_the_wrong_key_fails_the_key_row() -> None:
    data = _load()
    result = _check_vector(data, "C04")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.SIGNATURE_INVALID


def test_c05_recipient_not_on_the_list_is_could_not_check() -> None:
    data = _load()
    result = _check_vector(data, "C05")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c06_cites_another_permit_fails_the_permit_row() -> None:
    data = _load()
    result = _check_vector(data, "C06")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_PERMIT_MISMATCH


def test_c07_different_body_digest_fails_the_request_row() -> None:
    data = _load()
    result = _check_vector(data, "C07")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONTENT_MISMATCH


def test_c08_different_action_digest_fails_the_request_row() -> None:
    data = _load()
    result = _check_vector(data, "C08")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.ACTION_MISMATCH


def test_c09_two_different_effected_confirmations_for_one_permit_is_a_conflict() -> None:
    data = _load()
    v = data["vectors"]["C09"]
    conflicts = confirmation.find_reused_permits([v["confirmation"], v["second"]])
    assert conflicts == [("https://issuer.example", "p-0001")]


def test_c10_the_byte_identical_repeat_is_not_a_conflict() -> None:
    data = _load()
    v = data["vectors"]["C10"]
    conflicts = confirmation.find_reused_permits([v["confirmation"], v["second"]])
    assert conflicts == []


def test_c11_typ_is_the_permits_not_a_confirmations() -> None:
    data = _load()
    result = _check_vector(data, "C11")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED


def test_c12_effect_unknown_but_the_step_reported_ok_fails_the_outcome_row() -> None:
    data = _load()
    result = _check_vector(data, "C12", step_outcome_ok=True)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c13_refused_at_step_1_cites_nothing_and_passes() -> None:
    data = _load()
    result = _check_vector(data, "C13", step_outcome_ok=False)
    assert result.status is VerificationStatus.VERIFIED


def test_c14_an_unknown_member_is_named_not_failed() -> None:
    data = _load()
    result = _check_vector(data, "C14")
    assert result.status is VerificationStatus.VERIFIED
    assert "note" in result.detail


def test_c15_recipient_listed_but_not_its_kid_is_could_not_check() -> None:
    data = _load()
    result = _check_vector(data, "C15")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c16_no_recipient_list_given_is_could_not_check() -> None:
    data = _load()
    result = _check_vector(data, "C16")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c17_refused_while_in_progress_then_effected_is_not_a_conflict() -> None:
    data = _load()
    v = data["vectors"]["C17"]
    conflicts = confirmation.find_reused_permits([v["confirmation"], v["second"]])
    assert conflicts == []


def test_c18_another_recipients_iss_not_the_permits_aud_fails_the_permit_row() -> None:
    data = _load()
    result = _check_vector(data, "C18")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_PERMIT_MISMATCH


def test_c19_step_reported_error_but_holds_effected_fails_the_outcome_row() -> None:
    data = _load()
    result = _check_vector(data, "C19", step_outcome_ok=False)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c20_no_confirmation_recorded_is_could_not_check() -> None:
    data = _load()
    result = _check_vector(data, "C20", step_outcome_ok=True)
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c21_iat_an_hour_after_the_step_fails_the_request_row() -> None:
    data = _load()
    result = _check_vector(data, "C21")
    assert result.status is VerificationStatus.REFUSED


def test_every_vector_c01_to_c21_is_exercised() -> None:
    data = _load()
    assert set(data["vectors"]) == {f"C{i:02d}" for i in range(1, 22)}


# ---------------------------------------------------------------------------
# The recipient side: `confirmation.build`, given C01's step, reproduces C01.
# ---------------------------------------------------------------------------


def test_confirmation_build_matches_c01_byte_for_byte() -> None:
    data = _load()
    step = data["step"]
    keys = data["keys"]
    recipient_priv = ed25519.Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(keys["recipient"]["secret_hex"])
    )

    request = RecipientRequest(
        permit_token=step["permit"],
        method="POST",
        authority="payments.example",
        path="/v1/transfers",
        query="?",
        body=step["request"]["body"].encode(),
        content_digest_header=step["request"]["content-digest"],
        signature_input_header=step["request"]["signature-input"],
        signature_header=step["request"]["signature"],
        signature_created=1790000005,
        idempotency_key_header=step["request"]["idempotency-key"],
        recipient_audience="https://payments.example",
        action_object=step["action_object"],
    )
    from onedoor.permit import models as m
    from onedoor.permit import recipient as r

    issuer_table = {
        "https://issuer.example": m.IssuerTableEntry(
            issuer="https://issuer.example",
            public_key=bytes.fromhex(keys["issuer"]["public_hex"]),
            action_types=frozenset({"payments.transfer/1"}),
            limits={"payments.transfer/1": {"amount": {"currency": "EUR", "max": "1000.00"}}},
        )
    }
    result = r.verify(
        request,
        issuer_table=issuer_table,
        registry=m.REGISTRY,
        resolve_presenter_key=lambda jkt: bytes.fromhex(keys["presenter"]["public_hex"]),
        consume_store=r.InMemoryConsumeStore(),
        now=datetime.fromtimestamp(1790000006, tz=UTC),
        local_policy=lambda claims: True,
    )
    assert result.status is VerificationStatus.VERIFIED

    token = confirmation.build(
        request,
        result,
        recipient_key_id=keys["recipient"]["kid"],
        recipient_private_key=recipient_priv,
        now=datetime.fromtimestamp(1790000006, tz=UTC),
        outcome="effected",
        recipient_action_id="TX-0001",
    )
    assert token == data["vectors"]["C01"]["confirmation"]
