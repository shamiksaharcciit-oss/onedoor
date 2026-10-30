"""Confirmation-format test vectors (`confirmation_vectors_3.json`), re-verified
against this repository's own code -- the same promise `test_vectors.py` makes
for the other vector files, extended to cover the recipient confirmation
(bound-permit profile §10, closed by a separate, not-yet-public format note).

Three independent checks:

`test_confirmation_vectors_file_reproduces_from_this_repositorys_own_code`
ports the external generator's own algorithm (`gen_confirmation_vectors_3.py`),
using this repository's `onedoor.permit` modules directly rather than pointing
at an extracted sdist, and compares the resulting bytes against the committed
file.

`test_cNN_*` runs each vector through this repository's own
`onedoor.permit.confirmation.check` (single use through `find_reused_permits`
instead, for the three two-step vectors) -- onedoor's own four of the format
note's five rows; it does not implement the fifth (single use across many
confirmations) as one of `check`'s own rows, by design (see
`onedoor.permit.confirmation.find_reused_permits`).

`test_check_confirmation_rows_3_agrees_with_every_vectors_own_expectation`
runs `check_confirmation_rows_3.py` -- a second, independent implementation of
all five rows, written from the format note's text alone, importing nothing
from `onedoor` or `onetrace` -- against the committed file, and requires every
one of its 29 vectors' five rows to equal the file's own `expect`.

`test_confirmation_build_matches_c01_byte_for_byte` goes the other way: given
the shared step's real permit and request, run through this repository's own
`recipient.verify()`, `onedoor.permit.confirmation.build` must produce the
exact token C01 already carries.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
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
SHA256 = "d7b8c46b5dfe255c7826cd8581b98ac1896593e662cd50be13422968631fd92a"


def _load() -> dict:  # type: ignore[type-arg]
    return json.loads((VECTORS / "confirmation_vectors_3.json").read_text(encoding="utf-8"))


def test_confirmation_vectors_file_is_the_accepted_pack_byte_for_byte() -> None:
    data = (VECTORS / "confirmation_vectors_3.json").read_bytes()
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


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


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

    iss, aud, other = "https://issuer.example", "https://payments.example", "https://ledger.example"
    t0 = 1790000000
    started, ended = t0 + 4, t0 + 7
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

    def payload(**over):  # type: ignore[no-untyped-def]
        p: dict[str, object] = {
            "iss": aud,
            "permit": {"iss": iss, "jti": "p-0001", "digest": _sd(permit.encode("ascii"))},
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
        return p

    def build_confirmation(  # type: ignore[no-untyped-def]
        signer: str = "recipient",
        typ: str = "aadp-confirmation+jwt",
        header_extra: dict | None = None,
        **over,
    ):
        header = {
            "alg": "EdDSA",
            "kid": kid["other_recipient" if signer == "other_recipient" else "recipient"],
            "typ": typ,
        }
        header.update(header_extra or {})
        return jws.encode(header, payload(**over), priv[signer])

    def raw_confirmation(payload_json: str) -> str:
        """Signs a payload given as exact JSON text (a duplicate member can't live in a dict)."""
        header_b64 = _b64u(
            json.dumps(
                {"alg": "EdDSA", "kid": kid["recipient"], "typ": "aadp-confirmation+jwt"},
                separators=(",", ":"),
            ).encode()
        )
        payload_b64 = _b64u(payload_json.encode())
        signature = priv["recipient"].sign(f"{header_b64}.{payload_b64}".encode("ascii"))
        return f"{header_b64}.{payload_b64}.{_b64u(signature)}"

    def bare(**p):  # type: ignore[no-untyped-def]
        return jws.encode(
            {"alg": "EdDSA", "kid": kid["recipient"], "typ": "aadp-confirmation+jwt"},
            {"iss": aud, **p},
            priv["recipient"],
        )

    c_ok = build_confirmation()
    PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT-RUN"
    STEP = "approve_payment"
    RETRY = "approve_payment_retry"

    def one(outcome: str, token: str | None) -> list[dict]:  # type: ignore[type-arg]
        return [{"name": STEP, "outcome": outcome, "confirmation": token}]

    req1 = "1 confirmation(s) checked against the request its step sent"
    per1 = "1 confirmation(s) checked against the permit its step presented"
    key1 = "1 confirmation(s), each verifying under the recipient's listed key"
    su1 = "1 permit(s) cited, none confirmed as effected twice"
    out1 = "1 step(s), each outcome consistent with its confirmation"
    caution = "; signature not verified for: " + STEP

    def unverified(**kw):  # type: ignore[no-untyped-def]
        return rows(request=(PASS, req1 + caution), permit_=(PASS, per1 + caution), **kw)

    def rows(  # type: ignore[no-untyped-def]
        request=(PASS, req1),
        permit_=(PASS, per1),
        key=(PASS, key1),
        single=(PASS, su1),
        outcome=(PASS, out1),
    ):
        return {
            "request": list(request),
            "permit": list(permit_),
            "key": list(key),
            "single_use": list(single),
            "outcome": list(outcome),
        }

    no_conf = "no confirmation recorded"
    dup_json = json.dumps(payload(), separators=(",", ":"))
    dup_json = dup_json[:-1] + ',"outcome":"refused"}'  # "outcome" twice

    vectors = {
        "C01": {"case": "effected, every row passes", "steps": one("ok", c_ok), "expect": rows()},
        "C02": {
            "case": "refused at step 9 (no action_digest), the step reported an error",
            "steps": one(
                "error",
                build_confirmation(
                    outcome="refused",
                    reason="action-mismatch",
                    step=9,
                    recipient_action_id=None,
                    action_digest=None,
                ),
            ),
            "expect": rows(),
        },
        "C03": {
            "case": "refused at step 12, the step reported ok",
            "steps": one(
                "ok",
                build_confirmation(
                    outcome="refused", reason="local-policy", step=12, recipient_action_id=None
                ),
            ),
            "expect": rows(
                outcome=(
                    FAIL,
                    f"{STEP}: reported ok, but the recipient says 'refused' (local-policy, step 12)",
                )
            ),
        },
        "C04": {
            "case": "signed with the presenter's key, not the recipient's",
            "steps": one("ok", build_confirmation(signer="presenter")),
            "expect": unverified(
                key=(
                    FAIL,
                    f"{STEP}: the confirmation does not verify under the recipient's listed key",
                )
            ),
        },
        "C05": {
            "case": "recipient not on the list",
            "steps": one("ok", c_ok),
            "trust": {},
            "expect": unverified(key=(NOT_RUN, f"{STEP}: recipient {aud} is not on the list")),
        },
        "C06": {
            "case": "cites another permit",
            "steps": one(
                "ok",
                build_confirmation(
                    permit={"iss": iss, "jti": "p-0001", "digest": _sd(b"some-other-permit")}
                ),
            ),
            "expect": rows(permit_=(FAIL, f"{STEP}: the confirmation cites another permit")),
        },
        "C07": {
            "case": "a different request body digest",
            "steps": one(
                "ok",
                build_confirmation(
                    request={
                        "content_digest": _sd(body + b" "),
                        "signature_base_digest": _sd(base.encode()),
                    }
                ),
            ),
            "expect": rows(
                request=(FAIL, f"{STEP}: the recipient confirmed a different request body")
            ),
        },
        "C08": {
            "case": "a different action digest",
            "steps": one(
                "ok",
                build_confirmation(
                    action_digest=action_digest({**action_object, "amount_eur": "400.00"})
                ),
            ),
            "expect": rows(request=(FAIL, f"{STEP}: the recipient confirmed a different action")),
        },
        "C09": {
            "case": "two steps, same permit, two different effected confirmations",
            "steps": [
                {"name": STEP, "outcome": "ok", "confirmation": c_ok},
                {
                    "name": RETRY,
                    "outcome": "ok",
                    "confirmation": build_confirmation(recipient_action_id="TX-0002", iat=t0 + 7),
                },
            ],
            "expect": rows(
                request=(PASS, "2 confirmation(s) checked against the request their step sent"),
                permit_=(PASS, "2 confirmation(s) checked against the permit their step presented"),
                key=(PASS, "2 confirmation(s), each verifying under the recipient's listed key"),
                single=(FAIL, f"permit {iss} p-0001 confirmed as effected twice: {STEP}, {RETRY}"),
                outcome=(PASS, "2 step(s), each outcome consistent with its confirmation"),
            ),
        },
        "C10": {
            "case": "two steps, same permit, the byte-identical confirmation (a repeat)",
            "steps": [
                {"name": STEP, "outcome": "ok", "confirmation": c_ok},
                {"name": RETRY, "outcome": "ok", "confirmation": c_ok},
            ],
            "expect": rows(
                request=(PASS, "2 confirmation(s) checked against the request their step sent"),
                permit_=(PASS, "2 confirmation(s) checked against the permit their step presented"),
                key=(PASS, "2 confirmation(s), each verifying under the recipient's listed key"),
                single=(
                    PASS,
                    "1 permit(s) cited, none confirmed as effected twice (1 byte-identical repeat)",
                ),
                outcome=(PASS, "2 step(s), each outcome consistent with its confirmation"),
            ),
        },
        "C11": {
            "case": "typ is the permit's",
            "steps": one("ok", build_confirmation(typ="aadp-permit+jwt")),
            "expect": unverified(
                key=(FAIL, f"{STEP}: not a recipient confirmation (typ 'aadp-permit+jwt')")
            ),
        },
        "C12": {
            "case": "effect-unknown, the step reported ok",
            "steps": one(
                "ok", build_confirmation(outcome="effect-unknown", recipient_action_id=None)
            ),
            "expect": rows(
                outcome=(FAIL, f"{STEP}: reported ok, but the recipient says 'effect-unknown'")
            ),
        },
    }

    other_recipient = other
    vectors.update(
        {
            "C13": {
                "case": "refused at step 1: no permit, request or action members; iss and iat still checked",
                "steps": one(
                    "error", bare(outcome="refused", step=1, reason="malformed", iat=t0 + 6)
                ),
                "expect": rows(
                    request=(PASS, req1 + " (1 by date only)"),
                    permit_=(PASS, per1 + " (1 by recipient only)"),
                    single=(NOT_RUN, "no confirmation cites a permit"),
                ),
            },
            "C14": {
                "case": "an unknown payload member",
                "steps": one("ok", build_confirmation(note="x")),
                "expect": rows(key=(PASS, key1 + "; unknown member(s) ignored: note")),
            },
            "C15": {
                "case": "recipient on the list, its kid not listed",
                "steps": one("ok", c_ok),
                "trust": {aud: [kid["other_recipient"]]},
                "expect": unverified(
                    key=(NOT_RUN, f"{STEP}: key {kid['recipient'][:8]}... is not listed for {aud}")
                ),
            },
            "C16": {
                "case": "no recipient list given",
                "steps": one("ok", c_ok),
                "trust": None,
                "expect": unverified(key=(NOT_RUN, "no recipient list given (pass --recipients)")),
            },
            "C17": {
                "case": "refused at step 13 while the first presentation was in progress, then effected, "
                "same permit",
                "steps": [
                    {
                        "name": STEP,
                        "outcome": "error",
                        "confirmation": build_confirmation(
                            outcome="refused",
                            step=13,
                            reason="idempotency-conflict",
                            recipient_action_id=None,
                            iat=t0 + 5,
                        ),
                    },
                    {"name": RETRY, "outcome": "ok", "confirmation": c_ok},
                ],
                "expect": rows(
                    request=(PASS, "2 confirmation(s) checked against the request their step sent"),
                    permit_=(
                        PASS,
                        "2 confirmation(s) checked against the permit their step presented",
                    ),
                    key=(
                        PASS,
                        "2 confirmation(s), each verifying under the recipient's listed key",
                    ),
                    outcome=(PASS, "2 step(s), each outcome consistent with its confirmation"),
                ),
            },
            "C18": {
                "case": "signed by another listed recipient; its iss is not the permit's aud",
                "steps": one(
                    "ok", build_confirmation(signer="other_recipient", iss=other_recipient)
                ),
                "trust": {aud: [kid["recipient"]], other_recipient: [kid["other_recipient"]]},
                "expect": rows(
                    permit_=(
                        FAIL,
                        f"{STEP}: confirmed by {other_recipient}, but the permit is for {aud}",
                    )
                ),
            },
            "C19": {
                "case": "the step reported an error, but holds an effected confirmation",
                "steps": one("error", c_ok),
                "expect": rows(
                    outcome=(
                        FAIL,
                        f"{STEP}: reported error, but the recipient says it acted (TX-0001)",
                    )
                ),
            },
            "C20": {
                "case": "the step presented the permit and reported ok; no confirmation recorded",
                "steps": one("ok", None),
                "expect": rows(
                    request=(NOT_RUN, no_conf),
                    permit_=(NOT_RUN, no_conf),
                    key=(NOT_RUN, no_conf),
                    single=(NOT_RUN, no_conf),
                    outcome=(NOT_RUN, f"{STEP}: presented a permit; no confirmation recorded"),
                ),
            },
            "C21": {
                "case": "iat 3600 s after the step ended",
                "steps": one("ok", build_confirmation(iat=ended + 3600)),
                "expect": rows(
                    request=(
                        FAIL,
                        f"{STEP}: the confirmation is dated outside the step (iat 3600 s after it ended)",
                    )
                ),
            },
            "C22": {
                "case": "a crit header naming an extension this reader does not implement",
                "steps": one(
                    "ok", build_confirmation(header_extra={"crit": ["x-ext"], "x-ext": 1})
                ),
                "expect": unverified(
                    key=(FAIL, f"{STEP}: unknown critical header parameter(s): x-ext")
                ),
            },
            "C23": {
                "case": "effected without recipient_action_id (a section 2 violation)",
                "steps": one("ok", build_confirmation(recipient_action_id=None)),
                "expect": unverified(
                    key=(
                        FAIL,
                        f"{STEP}: malformed confirmation (effected without recipient_action_id)",
                    )
                ),
            },
            "C24": {
                "case": "a duplicate payload member: the confirmation is not read",
                "steps": one("ok", raw_confirmation(dup_json)),
                "expect": rows(
                    request=(NOT_RUN, "no readable confirmation"),
                    permit_=(NOT_RUN, "no readable confirmation"),
                    key=(FAIL, f"{STEP}: malformed confirmation (duplicate member 'outcome')"),
                    single=(NOT_RUN, "no readable confirmation"),
                    outcome=(NOT_RUN, f"{STEP}: the confirmation could not be read"),
                ),
            },
            "C25": {
                "case": "refused for a dependency (consume store), the step reported ok",
                "steps": one(
                    "ok",
                    build_confirmation(
                        outcome="refused", dependency="consume-store", recipient_action_id=None
                    ),
                ),
                "expect": rows(
                    outcome=(
                        FAIL,
                        f"{STEP}: reported ok, but the recipient could not check (consume-store)",
                    )
                ),
            },
            "C26": {
                "case": "typ written as the full media type",
                "steps": one("ok", build_confirmation(typ="application/aadp-confirmation+jwt")),
                "expect": unverified(
                    key=(
                        FAIL,
                        f"{STEP}: not a recipient confirmation (typ 'application/aadp-confirmation+jwt')",
                    )
                ),
            },
            "C27": {
                "case": "iat before the step started, outside the window",
                "steps": one("ok", build_confirmation(iat=started - 100)),
                "expect": rows(
                    request=(
                        FAIL,
                        f"{STEP}: the confirmation is dated outside the step (iat 100 s before it started)",
                    )
                ),
            },
            "C28": {
                "case": "a different signature base digest",
                "steps": one(
                    "ok",
                    build_confirmation(
                        request={
                            "content_digest": _sd(body),
                            "signature_base_digest": _sd(base.encode() + b"x"),
                        }
                    ),
                ),
                "expect": rows(
                    request=(FAIL, f"{STEP}: the recipient confirmed a different signature base")
                ),
            },
            "C29": {
                "case": "effect-unknown, the step reported an error",
                "steps": one(
                    "error", build_confirmation(outcome="effect-unknown", recipient_action_id=None)
                ),
                "expect": rows(),
            },
        }
    )

    out = {
        "format": "confirmation-vectors/3-draft",
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
        "window_seconds": 60,
        "step": {
            "started": started,
            "ended": ended,
            "permit_aud": aud,
            "permit_exp": t0 + 120,
            "permit": permit,
            "permit_iss": iss,
            "permit_jti": "p-0001",
            "permit_digest": _sd(permit.encode("ascii")),
            "action_object": action_object,
            "action_jcs": json.dumps(action_object, separators=(",", ":"), sort_keys=True),
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
        },
        "vectors": vectors,
    }
    return json.dumps(out, indent=1, sort_keys=True).encode("utf-8") + b"\n"


def test_confirmation_vectors_file_reproduces_from_this_repositorys_own_code() -> None:
    committed = (VECTORS / "confirmation_vectors_3.json").read_bytes()
    assert _rebuild_vectors_file() == committed


# ---------------------------------------------------------------------------
# A second, independent implementation of all five rows, written from the
# format note's text alone (vendored, not imported as a package) -- it must
# agree with the committed file's own stated `expect` for every vector.
# ---------------------------------------------------------------------------


def test_check_confirmation_rows_3_agrees_with_every_vectors_own_expectation() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_confirmation_rows_3", VECTORS / "check_confirmation_rows_3.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    data = _load()
    disagreements = []
    for vector_id, vector in sorted(data["vectors"].items()):
        got = module.rows(data, vector)
        if got != vector["expect"]:
            disagreements.append((vector_id, got, vector["expect"]))
    assert disagreements == [], disagreements


# ---------------------------------------------------------------------------
# One test per vector, through `onedoor.permit.confirmation.check` (C09/C10/C17
# through the single-use helper instead, since they are two-step pairs; onedoor's
# own `check` does not implement the single-use row itself).
# ---------------------------------------------------------------------------


def _recipients(data: dict, table) -> dict:  # type: ignore[no-untyped-def,type-arg]
    if table is None:
        return {}
    by_kid = {k["kid"]: bytes.fromhex(k["public_hex"]) for k in data["keys"].values()}
    return {iss: {kid: by_kid[kid] for kid in kids} for iss, kids in table.items()}


def _check_vector(data: dict, vector_id: str):  # type: ignore[no-untyped-def,type-arg]
    v = data["vectors"][vector_id]
    trust = v["trust"] if "trust" in v else data["trust"]
    step = data["step"]
    only_step = v["steps"][0]
    return confirmation.check(
        only_step["confirmation"],
        permit_token=step["permit"],
        permit_aud=step["permit_aud"],
        content_digest=step["content_digest"],
        signature_base=step["signature_base"],
        action_digest=step["action_digest"],
        step_started=step["started"],
        step_ended=step["ended"],
        step_outcome_ok=only_step["outcome"] == "ok",
        recipients=_recipients(data, trust),
    )


def test_c01_effected_every_row_passes() -> None:
    result = _check_vector(_load(), "C01")
    assert result.status is VerificationStatus.VERIFIED


def test_c02_refused_at_step_9_no_action_digest_step_error_passes() -> None:
    result = _check_vector(_load(), "C02")
    assert result.status is VerificationStatus.VERIFIED


def test_c03_refused_at_step_12_step_ok_fails_the_outcome_row() -> None:
    result = _check_vector(_load(), "C03")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c04_signed_by_the_wrong_key_fails_the_key_row() -> None:
    result = _check_vector(_load(), "C04")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.SIGNATURE_INVALID


def test_c05_recipient_not_on_the_list_is_could_not_check() -> None:
    result = _check_vector(_load(), "C05")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c06_cites_another_permit_fails_the_permit_row() -> None:
    result = _check_vector(_load(), "C06")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_PERMIT_MISMATCH


def test_c07_different_body_digest_fails_the_request_row() -> None:
    result = _check_vector(_load(), "C07")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONTENT_MISMATCH


def test_c08_different_action_digest_fails_the_request_row() -> None:
    result = _check_vector(_load(), "C08")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.ACTION_MISMATCH


def test_c09_two_different_effected_confirmations_for_one_permit_is_a_conflict() -> None:
    data = _load()
    steps = data["vectors"]["C09"]["steps"]
    conflicts = confirmation.find_reused_permits([s["confirmation"] for s in steps])
    assert conflicts == [("https://issuer.example", "p-0001")]


def test_c10_the_byte_identical_repeat_is_not_a_conflict() -> None:
    data = _load()
    steps = data["vectors"]["C10"]["steps"]
    conflicts = confirmation.find_reused_permits([s["confirmation"] for s in steps])
    assert conflicts == []


def test_c11_typ_is_the_permits_not_a_confirmations() -> None:
    result = _check_vector(_load(), "C11")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED


def test_c12_effect_unknown_but_the_step_reported_ok_fails_the_outcome_row() -> None:
    result = _check_vector(_load(), "C12")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c13_refused_at_step_1_cites_nothing_and_passes() -> None:
    result = _check_vector(_load(), "C13")
    assert result.status is VerificationStatus.VERIFIED


def test_c14_an_unknown_member_is_named_not_failed() -> None:
    result = _check_vector(_load(), "C14")
    assert result.status is VerificationStatus.VERIFIED
    assert "note" in result.detail


def test_c15_recipient_listed_but_not_its_kid_is_could_not_check() -> None:
    result = _check_vector(_load(), "C15")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c16_no_recipient_list_given_is_could_not_check() -> None:
    result = _check_vector(_load(), "C16")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c17_refused_while_in_progress_then_effected_is_not_a_conflict() -> None:
    data = _load()
    steps = data["vectors"]["C17"]["steps"]
    conflicts = confirmation.find_reused_permits([s["confirmation"] for s in steps])
    assert conflicts == []


def test_c18_another_recipients_iss_not_the_permits_aud_fails_the_permit_row() -> None:
    result = _check_vector(_load(), "C18")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_PERMIT_MISMATCH


def test_c19_step_reported_error_but_holds_effected_fails_the_outcome_row() -> None:
    result = _check_vector(_load(), "C19")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH


def test_c20_no_confirmation_recorded_is_could_not_check() -> None:
    result = _check_vector(_load(), "C20")
    assert result.status is VerificationStatus.COULD_NOT_CHECK


def test_c21_iat_an_hour_after_the_step_fails_the_request_row() -> None:
    result = _check_vector(_load(), "C21")
    assert result.status is VerificationStatus.REFUSED


def test_c22_an_unimplemented_crit_extension_fails_the_key_row() -> None:
    result = _check_vector(_load(), "C22")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED


def test_c23_effected_with_no_recipient_action_id_is_malformed() -> None:
    result = _check_vector(_load(), "C23")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED


def test_c24_a_duplicate_payload_member_is_malformed() -> None:
    result = _check_vector(_load(), "C24")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED
    assert "duplicate" in result.detail


def test_c25_refused_for_a_dependency_but_the_step_reported_ok_fails_the_outcome_row() -> None:
    result = _check_vector(_load(), "C25")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONFIRMATION_OUTCOME_MISMATCH
    assert "could not check" in result.detail
    assert "consume-store" in result.detail


def test_c26_typ_as_the_full_media_type_fails_the_key_row() -> None:
    result = _check_vector(_load(), "C26")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.MALFORMED


def test_c27_iat_before_the_step_started_fails_the_request_row() -> None:
    result = _check_vector(_load(), "C27")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONTENT_MISMATCH


def test_c28_a_different_signature_base_digest_fails_the_request_row() -> None:
    result = _check_vector(_load(), "C28")
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is confirmation.RefusalReason.CONTENT_MISMATCH
    assert "signature base" in result.detail


def test_c29_effect_unknown_step_error_passes() -> None:
    result = _check_vector(_load(), "C29")
    assert result.status is VerificationStatus.VERIFIED


def test_every_vector_c01_to_c29_is_exercised() -> None:
    data = _load()
    assert set(data["vectors"]) == {f"C{i:02d}" for i in range(1, 30)}


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
    assert token == data["vectors"]["C01"]["steps"][0]["confirmation"]
