"""Confirmation-format test vectors, draft 4 (`confirmation_vectors_4.json`,
format `confirmation-vectors/4-draft`). Draft 4 adds C30-C54 to draft 3's
C01-C29 (unchanged, token and expectation) to exercise every problem format
note section 2.4's table names, each with its exact text. The generator is not
shipped code and is not kept in this repository (the format note's own pack,
outside it) -- the same arrangement `confirmation_vectors_3.json` already
follows; see `test_confirmation_vectors.py` for that file's own, separate
"reproduces from this repository's own code" check, which draft 3's inline
generator port makes possible there.

`test_check_confirmation_rows_4_agrees_with_every_vectors_own_expectation` is
the second, independent implementation (`check_confirmation_rows_4.py`,
imports nothing from `onedoor`/`onetrace`) agreeing with the committed file's
own `expect` for all 54 vectors' five rows.

`test_c_nn_*` runs each of the 51 one-step vectors through this repository's
own `onedoor.permit.confirmation.check`, asserting its status, reason and step
(C09, C10 and C17 are two-step pairs, exercised through `find_reused_permits`
instead in `test_confirmation_vectors.py`, same as for draft 3 -- draft 4 does
not change them). For every vector whose key row is `malformed confirmation
(<problem>)`, the exact `<problem>` text is asserted too: that text, verbatim
by section, is the whole of what draft 4 adds over draft 3.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from onedoor.permit import confirmation
from onedoor.permit.models import RefusalReason, VerificationStatus

VECTORS = Path(__file__).parent
SHA256 = "52bc2e98762676c7f975f18125ef99cf9dcca0afab323b0f5e175debcd58ed14"

VERIFIED = VerificationStatus.VERIFIED
REFUSED = VerificationStatus.REFUSED
COULD_NOT_CHECK = VerificationStatus.COULD_NOT_CHECK
MALFORMED = RefusalReason.MALFORMED


def _load() -> dict:  # type: ignore[type-arg]
    return json.loads((VECTORS / "confirmation_vectors_4.json").read_text(encoding="utf-8"))


def test_confirmation_vectors_4_file_is_the_accepted_pack_byte_for_byte() -> None:
    data = (VECTORS / "confirmation_vectors_4.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA256


def test_check_confirmation_rows_4_agrees_with_every_vectors_own_expectation() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_confirmation_rows_4", VECTORS / "check_confirmation_rows_4.py"
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


# vector id -> (status, reason, step, detail-if-malformed-else-None)
_EXPECTED: dict[str, tuple[VerificationStatus, RefusalReason | None, int | None, str | None]] = {
    "C01": (VERIFIED, None, None, None),
    "C02": (VERIFIED, None, None, None),
    "C03": (REFUSED, RefusalReason.CONFIRMATION_OUTCOME_MISMATCH, 4, None),
    "C04": (REFUSED, RefusalReason.SIGNATURE_INVALID, 1, None),
    "C05": (COULD_NOT_CHECK, None, None, None),
    "C06": (REFUSED, RefusalReason.CONFIRMATION_PERMIT_MISMATCH, 2, None),
    "C07": (REFUSED, RefusalReason.CONTENT_MISMATCH, 3, None),
    "C08": (REFUSED, RefusalReason.ACTION_MISMATCH, 3, None),
    "C11": (REFUSED, MALFORMED, 1, None),
    "C12": (REFUSED, RefusalReason.CONFIRMATION_OUTCOME_MISMATCH, 4, None),
    "C13": (VERIFIED, None, None, None),
    "C14": (VERIFIED, None, None, None),
    "C15": (COULD_NOT_CHECK, None, None, None),
    "C16": (COULD_NOT_CHECK, None, None, None),
    "C18": (REFUSED, RefusalReason.CONFIRMATION_PERMIT_MISMATCH, 2, None),
    "C19": (REFUSED, RefusalReason.CONFIRMATION_OUTCOME_MISMATCH, 4, None),
    "C20": (COULD_NOT_CHECK, None, None, None),
    "C21": (REFUSED, RefusalReason.CONTENT_MISMATCH, 3, None),
    "C22": (REFUSED, MALFORMED, 1, None),
    "C23": (REFUSED, MALFORMED, 1, "malformed confirmation (effected without recipient_action_id)"),
    "C24": (REFUSED, MALFORMED, 1, "malformed confirmation (duplicate member 'outcome')"),
    "C25": (REFUSED, RefusalReason.CONFIRMATION_OUTCOME_MISMATCH, 4, None),
    "C26": (REFUSED, MALFORMED, 1, None),
    "C27": (REFUSED, RefusalReason.CONTENT_MISMATCH, 3, None),
    "C28": (REFUSED, RefusalReason.CONTENT_MISMATCH, 3, None),
    "C29": (VERIFIED, None, None, None),
    "C30": (VERIFIED, None, None, None),
    "C31": (VERIFIED, None, None, None),
    "C32": (REFUSED, MALFORMED, 1, "malformed confirmation (alg 'HS256')"),
    "C33": (REFUSED, MALFORMED, 1, "malformed confirmation (alg 'none')"),
    "C34": (REFUSED, MALFORMED, 1, "malformed confirmation (alg None)"),
    "C35": (REFUSED, MALFORMED, 1, "malformed confirmation (iat missing or not an integer)"),
    "C36": (REFUSED, MALFORMED, 1, "malformed confirmation (iat missing or not an integer)"),
    "C37": (REFUSED, MALFORMED, 1, "malformed confirmation (iat missing or not an integer)"),
    "C38": (REFUSED, MALFORMED, 1, "malformed confirmation (iss missing or not a string)"),
    "C39": (REFUSED, MALFORMED, 1, "malformed confirmation (outcome missing or unknown)"),
    "C40": (REFUSED, MALFORMED, 1, "malformed confirmation (permit missing)"),
    "C41": (REFUSED, MALFORMED, 1, "malformed confirmation (action_digest missing)"),
    "C42": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (step, reason or dependency on a 'effected' confirmation)",
    ),
    "C43": (REFUSED, MALFORMED, 1, "malformed confirmation (request.content_digest missing)"),
    "C44": (REFUSED, MALFORMED, 1, "malformed confirmation (permit is not an object)"),
    "C45": (REFUSED, MALFORMED, 1, "malformed confirmation (permit.jti not a string)"),
    "C46": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (recipient_action_id on a 'effect-unknown' confirmation)",
    ),
    "C47": (REFUSED, MALFORMED, 1, "malformed confirmation (step missing or outside 1 to 13)"),
    "C48": (REFUSED, MALFORMED, 1, "malformed confirmation (step missing or outside 1 to 13)"),
    "C49": (REFUSED, MALFORMED, 1, "malformed confirmation (reason missing)"),
    "C50": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (action_digest present before its step passed)",
    ),
    "C51": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (permit present before its step passed)",
    ),
    "C52": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (request.signature_base_digest present before its step passed)",
    ),
    "C53": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (both a check refusal and a dependency)",
    ),
    "C54": (
        REFUSED,
        MALFORMED,
        1,
        "malformed confirmation (a refusal with neither step and reason nor a known dependency)",
    ),
}


@pytest.mark.parametrize("vector_id", sorted(_EXPECTED, key=lambda v: int(v[1:])))
def test_one_step_vector_status_reason_step(vector_id: str) -> None:
    data = _load()
    result = _check_vector(data, vector_id)
    status, reason, step, detail = _EXPECTED[vector_id]
    assert result.status is status
    assert result.reason is reason
    assert result.step == step
    if detail is not None:
        assert result.detail == detail


def test_every_one_step_vector_of_draft_4_is_exercised() -> None:
    data = _load()
    one_step = {vid for vid, v in data["vectors"].items() if len(v["steps"]) == 1}
    assert one_step == set(_EXPECTED)
    assert len(one_step) == 51


def test_draft_4_has_54_vectors_c01_to_c54() -> None:
    data = _load()
    assert set(data["vectors"]) == {f"C{i:02d}" for i in range(1, 55)}
