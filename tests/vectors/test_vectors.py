"""Every vector in this directory, re-verified against the real functions it was
generated from. A vendoring consumer trusts these files without running
onedoor at all; this module is what earns that trust here, in this repo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from onedoor.decision_digest import decision_digest
from onedoor.decision_ref import check, check_files
from onedoor.permit import jws
from onedoor.permit.action import action_digest

VECTORS = Path(__file__).parent


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# action_digests.json
# --------------------------------------------------------------------------


def test_action_digest_vectors_reproduce_exactly() -> None:
    data = _load("action_digests.json")
    assert data["vectors"], "the vector list must not be empty"
    for vector in data["vectors"]:
        recomputed = action_digest(vector["action_object"])
        assert recomputed == vector["action_digest"], vector["id"]


def test_action_digest_vectors_are_not_trivially_equal() -> None:
    """A regression that made every digest the same constant would still pass
    the test above for each vector individually -- this catches that."""
    data = _load("action_digests.json")
    digests = {v["action_digest"] for v in data["vectors"]}
    assert len(digests) == len(data["vectors"]), "every action object must digest distinctly"


# --------------------------------------------------------------------------
# decision_refs.json
# --------------------------------------------------------------------------


def test_decision_ref_vectors_give_their_claimed_outcome() -> None:
    data = _load("decision_refs.json")
    rows = data["export_rows"]
    for case in data["cases"]:
        if case["id"] == "export_damaged":
            continue  # a file-level property, checked separately below
        result = check(case["ref"], rows)
        assert result.status == case["expected"], (case["id"], result)


def test_export_damaged_is_a_file_property_not_a_row_property(tmp_path: Path) -> None:
    data = _load("decision_refs.json")
    case = next(c for c in data["cases"] if c["id"] == "export_damaged")
    good_line = json.dumps(data["export_rows"][0], sort_keys=True, separators=(",", ":"))
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(good_line + "\n", encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(json.dumps(case["ref"]), encoding="utf-8")

    # A sidecar naming a digest the file does not actually have.
    sidecar_path = tmp_path / "export.jsonl.sha256"
    sidecar_path.write_text("0" * 64 + "  export.jsonl\n", encoding="utf-8")

    result = check_files(export_path, ref_path)
    assert result.status == "export_damaged"


# --------------------------------------------------------------------------
# permits.json
# --------------------------------------------------------------------------


def test_permit_vector_verifies_with_the_matching_action_object() -> None:
    data = _load("permits.json")
    issuer_pub = _jwk_to_raw(data["issuer_public_key_jwk"])
    token = data["permit_token"]
    _, claims = jws.verify(token, issuer_pub)

    verifies_case = next(c for c in data["cases"] if c["id"] == "verifies")
    recomputed = action_digest(verifies_case["action_object"])
    assert recomputed == claims["action_digest"]
    assert datetime.fromisoformat(verifies_case["check_at"]) < datetime.fromtimestamp(
        claims["exp"], tz=UTC
    )


def test_permit_vector_with_a_changed_amount_no_longer_matches_the_claim() -> None:
    data = _load("permits.json")
    issuer_pub = _jwk_to_raw(data["issuer_public_key_jwk"])
    _, claims = jws.verify(data["permit_token"], issuer_pub)

    changed_case = next(c for c in data["cases"] if c["id"] == "changed_amount")
    recomputed = action_digest(changed_case["action_object"])
    assert recomputed != claims["action_digest"], (
        "the changed-amount case must NOT reproduce the signed action digest"
    )


def test_permit_vector_is_expired_at_its_recorded_check_time() -> None:
    data = _load("permits.json")
    issuer_pub = _jwk_to_raw(data["issuer_public_key_jwk"])
    _, claims = jws.verify(data["permit_token"], issuer_pub)

    expired_case = next(c for c in data["cases"] if c["id"] == "expired")
    check_at = datetime.fromisoformat(expired_case["check_at"])
    assert check_at > datetime.fromtimestamp(claims["exp"], tz=UTC)


def test_permit_vector_rejects_the_wrong_issuer_key() -> None:
    """The negative control for signature verification itself."""
    data = _load("permits.json")
    wrong_key = bytes((b ^ 0xFF) for b in _jwk_to_raw(data["issuer_public_key_jwk"]))
    with pytest.raises(Exception):  # jws.verify's own InvalidSignature/MalformedJWS
        jws.verify(data["permit_token"], wrong_key)


def _jwk_to_raw(jwk_obj: dict) -> bytes:  # type: ignore[type-arg]
    import base64

    x = jwk_obj["x"] + "=" * (-len(jwk_obj["x"]) % 4)
    return base64.urlsafe_b64decode(x)


# --------------------------------------------------------------------------
# preimage_v6.json
# --------------------------------------------------------------------------


def test_preimage_v6_vectors_reproduce_exactly() -> None:
    data = _load("preimage_v6.json")
    for row in data["rows"]:
        recomputed = decision_digest(row["row"])
        assert recomputed == row["decision_digest"], row["id"]


def test_pre_v6_row_digest_is_unchanged_by_migrating() -> None:
    data = _load("preimage_v6.json")
    by_id = {r["id"]: r for r in data["rows"]}
    before = by_id["pre_v6_row_before_migrating"]
    after = by_id["pre_v6_row_after_migrating"]
    assert before["decision_digest"] == after["decision_digest"]
    assert "resume_digest_expected" not in before["row"]
    assert "resume_digest_expected" not in after["row"]


def test_v6_mismatch_row_includes_the_new_columns_in_its_digest() -> None:
    data = _load("preimage_v6.json")
    by_id = {r["id"]: r for r in data["rows"]}
    mismatch_row = by_id["v6_row_resume_mismatch"]
    assert mismatch_row["row"]["resume_digest_expected"] is not None
    assert mismatch_row["row"]["resume_digest_actual"] is not None

    tampered = dict(mismatch_row["row"])
    tampered["resume_digest_actual"] = "sha256:" + "f" * 64
    assert decision_digest(tampered) != mismatch_row["decision_digest"], (
        "tampering with a hashed column must move the digest"
    )
