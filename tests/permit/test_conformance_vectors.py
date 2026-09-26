"""Bound-permit profile §16 conformance vectors, traced against this package's
actual test coverage.

`vectors/manifest.json` is the vector table verbatim (id, mutation, expected
outcome) as a data file, per the ticket's own requirement that vectors live as
data rather than only as prose. `VECTOR_STATUS` below is this file's traceability
claim: which vectors are exercised by a real test (naming it), and which are a
disclosed gap (naming why). The one check in this file is that every vector in
the manifest has an entry in `VECTOR_STATUS` -- a vector silently dropped from
both would be exactly the "unverifiable collapsed into passing" failure this
project's own discipline exists to catch.

V02, V12, V23 and V24's "not consumed" half did not have a dedicated test before
this file; they do now, in this module. Every other implemented vector is
already covered in `test_recipient.py`, named here rather than duplicated.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from onedoor.permit.models import RefusalReason, VerificationStatus
from tests.permit.test_recipient import _build, _verify

MANIFEST = json.loads((Path(__file__).parent / "vectors" / "manifest.json").read_text())
VECTOR_IDS = {v["id"] for v in MANIFEST["vectors"]}

IMPLEMENTED = "implemented"
GAP = "gap"

VECTOR_STATUS: dict[str, tuple[str, str]] = {
    "V01": (
        IMPLEMENTED,
        "test_recipient.py::test_a_body_that_does_not_match_content_digest_is_refused",
    ),
    "V02": (IMPLEMENTED, "this file::test_v02_path_changed_after_signing"),
    "V03": (IMPLEMENTED, "test_recipient.py::test_the_wrong_audience_is_refused"),
    "V04": (IMPLEMENTED, "test_recipient.py::test_a_list_valued_audience_is_refused"),
    "V05": (IMPLEMENTED, "test_recipient.py::test_an_expired_permit_is_refused"),
    "V06": (IMPLEMENTED, "test_recipient.py::test_a_lifetime_longer_than_the_ceiling_is_refused"),
    "V07": (
        IMPLEMENTED,
        "test_recipient.py::test_a_repeated_presentation_with_the_same_content_digest_returns_the_stored_result",
    ),
    "V08": (
        IMPLEMENTED,
        "test_recipient.py::test_a_replay_with_a_different_content_digest_is_an_idempotency_conflict",
    ),
    "V09": (
        IMPLEMENTED,
        "test_recipient.py::test_the_wrong_presenter_key_is_refused -- see the open "
        "question in docs/design/bound-permit-next.md about this vector's overlap "
        "with test_a_request_signed_by_the_wrong_key_is_refused (REQUEST_SIGNATURE_INVALID)",
    ),
    "V10": (IMPLEMENTED, "test_recipient.py::test_a_missing_http_signature_is_refused"),
    "V11": (
        IMPLEMENTED,
        "test_recipient.py::test_a_covered_component_dropped_from_signature_input_is_binding_incomplete",
    ),
    "V12": (IMPLEMENTED, "this file::test_v12_semantically_equal_but_differently_serialised_body"),
    "V13": (IMPLEMENTED, "test_recipient.py::test_an_action_object_mismatch_is_refused"),
    "V14": (IMPLEMENTED, "test_recipient.py::test_an_unregistered_authorization_type_is_refused"),
    "V15": (
        IMPLEMENTED,
        "test_recipient.py::test_an_action_type_outside_the_issuer_table_is_out_of_scope",
    ),
    "V16": (
        IMPLEMENTED,
        "test_recipient.py::test_an_amount_over_the_issuers_limit_is_out_of_scope",
    ),
    "V17": (
        GAP,
        "no status mechanism is implemented (currentness is always 'time-bounded' or "
        "an unimplemented 'status-checked'); STALE_POLICY is unreachable. See "
        "docs/design/bound-permit-next.md §7.",
    ),
    "V18": (IMPLEMENTED, "test_recipient.py::test_status_checked_currentness_could_not_be_checked"),
    "V19": (IMPLEMENTED, "test_recipient.py::test_a_mandate_digest_mismatch_is_refused"),
    "V20": (IMPLEMENTED, "test_recipient.py::test_a_mandate_pending_is_refused"),
    "V21": (IMPLEMENTED, "test_recipient.py::test_a_chained_permit_is_refused_structurally"),
    "V22": (
        GAP,
        "the joint record (recipient confirmation) is not implemented -- there is no "
        "presenter-side check to write. See docs/design/bound-permit-next.md §10.",
    ),
    "V23": (IMPLEMENTED, "this file::test_v23_consume_store_unavailable_is_could_not_check"),
    "V24": (IMPLEMENTED, "this file::test_v24_a_local_policy_refusal_never_consumes_the_permit"),
}


def test_every_vector_in_the_manifest_has_a_traced_status() -> None:
    assert set(VECTOR_STATUS) == VECTOR_IDS, (
        "a vector was added to the manifest with no status here"
    )


def test_the_gap_count_matches_what_the_report_should_say() -> None:
    implemented = sum(1 for status, _ in VECTOR_STATUS.values() if status == IMPLEMENTED)
    gaps = sum(1 for status, _ in VECTOR_STATUS.values() if status == GAP)
    assert implemented == 22
    assert gaps == 2
    assert implemented + gaps == len(VECTOR_IDS) == 24


# --- V02: path changed after signing -----------------------------------------------


def test_v02_path_changed_after_signing() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, path="/a-different-path"))
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID
    assert result.step == 8


# --- V12: same meaning, different bytes ---------------------------------------------


def test_v12_semantically_equal_but_differently_serialised_body() -> None:
    """The recipient compares bytes, never parsed meaning: `{"a":1,"b":2}` and
    `{"b": 2, "a": 1}` describe the same JSON value but are different bytes, and
    Content-Digest is computed over exactly what was received (profile §4.1)."""
    original = b'{"a":1,"b":2}'
    reserialised = b'{"b": 2, "a": 1}'
    assert original != reserialised

    fx = _build(body=original)
    fx = replace(fx, request=replace(fx.request, body=reserialised))
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.CONTENT_MISMATCH
    assert result.step == 7


# --- V23: consume store unavailable --------------------------------------------------


class _BrokenConsumeStore:
    """Every operation raises -- a store that is down, not merely empty."""

    def get(self, iss: str, jti: str) -> None:
        raise RuntimeError("consume store unreachable")

    def put(self, iss: str, jti: str, consumption: object) -> None:
        raise RuntimeError("consume store unreachable")

    def in_progress(self, iss: str, jti: str) -> bool:
        raise RuntimeError("consume store unreachable")

    def mark_in_progress(self, iss: str, jti: str) -> None:
        raise RuntimeError("consume store unreachable")


def test_v23_consume_store_unavailable_is_could_not_check() -> None:
    fx = _build()
    result = _verify(fx, consume_store=_BrokenConsumeStore())
    assert result.status is VerificationStatus.COULD_NOT_CHECK
    assert result.dependency == "consume-store"
    assert result.reason is None, "could-not-check never also carries a refusal reason"


# --- V24: a local-policy refusal never consumes the permit ---------------------------


def test_v24_a_local_policy_refusal_never_consumes_the_permit() -> None:
    from onedoor.permit.recipient import InMemoryConsumeStore

    fx = _build()
    store = InMemoryConsumeStore()
    refused = _verify(fx, consume_store=store, local_policy=lambda claims: False)
    assert refused.reason is RefusalReason.LOCAL_POLICY

    # If step 12 had run after step 13, a second presentation would see a stored
    # (verified) result. It must instead re-run the same refusal every time.
    again = _verify(fx, consume_store=store, local_policy=lambda claims: False)
    assert again.reason is RefusalReason.LOCAL_POLICY
    assert again.repeat is False
