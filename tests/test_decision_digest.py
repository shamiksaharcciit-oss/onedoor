"""onedoor.decision_digest: the one function both the decide path and the export
call, so a decision reference computed at decide time and a digest recomputed
later from an export can never disagree about what "the row" was.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from onedoor.decision_digest import canonical_row_json, canonical_row_record, decision_digest


def test_decision_digest_is_sha256_with_a_declared_prefix() -> None:
    row = {"id": 1, "kind": "decision"}
    result = decision_digest(row)
    assert result.startswith("sha256:")
    expected = hashlib.sha256(canonical_row_json(canonical_row_record(row))).hexdigest()
    assert result == f"sha256:{expected}"


def test_key_order_does_not_change_the_digest() -> None:
    a = decision_digest({"id": 1, "kind": "decision", "request_id": "x"})
    b = decision_digest({"request_id": "x", "kind": "decision", "id": 1})
    assert a == b


def test_changing_one_value_changes_the_digest() -> None:
    a = decision_digest({"id": 1, "detail": "one"})
    b = decision_digest({"id": 1, "detail": "two"})
    assert a != b


def test_a_float_anywhere_in_the_row_is_refused() -> None:
    with pytest.raises(TypeError, match="float"):
        decision_digest({"id": 1, "cost_eur": 4.5})


def test_null_valued_chaining_columns_hash_the_same_as_an_explicit_none() -> None:
    """The function does not branch on whether chaining is enabled -- a row with
    chaining columns present-but-NULL (chaining off) and a row that never had
    those keys at all are different *rows* (different column sets), but a row
    read back from SQLite always carries every column, NULL or not -- this
    confirms NULL columns serialize as ordinary JSON `null`, not specially."""
    row = {"id": 1, "row_hash": None, "prev_hash": None, "seq": None}
    record = canonical_row_record(row)
    assert json.loads(canonical_row_json(record)) == {
        "id": 1,
        "row_hash": None,
        "prev_hash": None,
        "seq": None,
    }


def test_a_populated_chaining_row_and_a_null_chaining_row_get_different_digests() -> None:
    """Not a claim that chaining is invisible to the digest -- the whole row is
    hashed, chaining columns included -- only that the FUNCTION applies
    uniformly whether or not chaining happens to be configured for this
    deployment."""
    off = decision_digest({"id": 1, "row_hash": None, "seq": None})
    on = decision_digest({"id": 1, "row_hash": "abc123", "seq": 1})
    assert off != on
