"""The preimage, checked against a second implementation and four golden vectors.

R031 §1.3 asks for the spec in one place with test vectors. This file supplies the
harder half of P2-06: **a second implementation written from `docs/row-preimage.md`
rather than from `onedoor/guardrail/preimage.py`.** An implementation that agrees with
itself has proved nothing. The forensics channel put it best and core adopted the
sentence: *an implementation that verifies because it was fitted to the artifact is not
independent of it.*

So `_from_the_document` below is deliberately built a different way — it walks a
declared table of field names taken from the document, encodes with explicit slicing
rather than helper calls, and never imports the production encoder. If the two agree on
generated rows and on the vectors, the document says what the code does. If they
disagree, the document is wrong, the code is wrong, or the document is ambiguous — and
all three are things to find now rather than after the first chained row.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from random import Random
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.guardrail.preimage import (
    EXCLUDED,
    FIELD_ORDER,
    encode_field,
    preimage,
    row_hash,
)
from tests.conftest import FROZEN_NOW, make_request

SPEC = Path(__file__).resolve().parents[2] / "docs" / "row-preimage.md"


# --- The second implementation, from the document -------------------------------


def _doc_field_order() -> list[str]:
    """Read §3's table out of the document itself, so the two orders cannot drift.

    If someone reorders `FIELD_ORDER` without touching the spec, this returns the old
    order and every comparison below fails. That is the intended failure: the document
    is normative, and code that disagrees with it is the thing that is wrong.
    """
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("## 3. Field order", 1)[1].split("## 4.", 1)[0]
    return [m.group(1) for m in re.finditer(r"^\| *\d+ *\| *`([a-z_]+)` *\|", section, re.M)]


def _from_the_document(values: dict[str, object]) -> bytes:
    """Build the preimage by following docs/row-preimage.md §2 and §3 literally.

    Written to be structurally unlike the production encoder: an explicit accumulator,
    an inline type ladder, and byte constants spelled out rather than imported.
    """
    out = bytearray()
    out += "onedoor/row-preimage/1".encode("ascii")
    for name in _doc_field_order():
        value = values[name]
        if value is None:
            out += bytes([0x00])
            continue
        if isinstance(value, bytes):
            payload = value
        elif value is True:
            payload = b"1"
        elif value is False:
            payload = b"0"
        elif isinstance(value, int):
            payload = format(value, "d").encode("ascii")
        elif isinstance(value, str):
            payload = value.encode("utf-8")
        else:  # pragma: no cover - the document declares no other column type
            raise TypeError(name)
        out += bytes([0x01])
        length = len(payload)
        out += bytes(
            (
                (length >> 56) & 0xFF,
                (length >> 48) & 0xFF,
                (length >> 40) & 0xFF,
                (length >> 32) & 0xFF,
                (length >> 24) & 0xFF,
                (length >> 16) & 0xFF,
                (length >> 8) & 0xFF,
                length & 0xFF,
            )
        )
        out += payload
    return bytes(out)


def _blank() -> dict[str, object]:
    return dict.fromkeys(FIELD_ORDER, None)


def _sample(**overrides: object) -> dict[str, object]:
    values = _blank()
    values.update(
        {
            "seq": 1,
            "prev_hash": "0" * 64,
            "request_id": "8e2a1c44-0000-4000-8000-00000000abcd",
            "kind": "decision",
            "action_type": "demo.spend",
            "source": "llm",
            "params_json": '{"amount_eur":"9"}',
            "decision": "denied",
            "reason_code": "cap_value",
            "nominal_tier": 2,
            "effective_tier": 2,
            "detail": "",
            "created_at": "2026-07-05T12:00:00Z",
            "policy_version": "a" * 64,
            "protocol": "aadp/0.2",
            "params_provenance": "serialized",
        }
    )
    values.update(overrides)
    return values


# --- The document is a definition, not a description ----------------------------


def test_the_document_and_the_module_declare_the_same_field_order() -> None:
    assert _doc_field_order() == list(FIELD_ORDER), (
        "docs/row-preimage.md §3 and preimage.FIELD_ORDER disagree. The document is "
        "normative; reordering fields is a new preimage version, not a refactor."
    )


def test_the_second_implementation_agrees_on_a_realistic_row() -> None:
    values = _sample()
    assert _from_the_document(values) == preimage(values)


def test_the_second_implementation_agrees_on_generated_rows() -> None:
    """Generated inputs, not hand-picked ones: spot-checks find only what you thought of."""
    rng = Random(20260822)
    alphabet = 'ab{}"\\ €\x00\x01\n' + "".join(chr(c) for c in range(0x20, 0x30))
    for _ in range(200):
        values = _blank()
        for name in FIELD_ORDER:
            roll = rng.random()
            if roll < 0.25:
                continue  # leave it NULL
            if roll < 0.35:
                values[name] = ""
            elif roll < 0.45:
                values[name] = rng.randint(-5, 10_000)
            elif roll < 0.5:
                values[name] = rng.choice([True, False])
            elif roll < 0.55:
                values[name] = bytes(rng.randrange(256) for _ in range(rng.randint(0, 12)))
            else:
                values[name] = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 20)))
        assert _from_the_document(values) == preimage(values)


# --- Golden vectors (R031 §1.3), each named for the attack it refuses ------------


def test_vector_shift_collision() -> None:
    """`("a","bc")` and `("ab","c")` must not collide.

    The classic failure of naive concatenation, and the whole reason a length prefix
    exists. Asserted on adjacent fields so the two rows differ ONLY in where the split
    falls.
    """
    left = _sample(malformed_kind="a", canon_schema="bc")
    right = _sample(malformed_kind="ab", canon_schema="c")
    assert row_hash(left) != row_hash(right)
    assert _from_the_document(left) != _from_the_document(right)


def test_vector_absent_versus_empty() -> None:
    """R031 §1.1. NULL is not a zero-length string, and the bytes must say so."""
    absent = _sample(detail=None)
    empty = _sample(detail="")
    assert row_hash(absent) != row_hash(empty)
    assert encode_field(None) == b"\x00"
    assert encode_field("") == b"\x01" + b"\x00" * 8
    assert encode_field(None)[0] != encode_field("")[0], (
        "absent and empty must differ in the FIRST byte, not merely in total length"
    )


def test_vector_a_value_containing_header_bytes() -> None:
    """A field whose CONTENT is a tag-plus-length header must not be confusable with one.

    `params_json` is received data: an attacker chooses these bytes and will choose
    them to look like framing if framing can be faked. Fixed-width prefixes make it
    structurally impossible; this proves it rather than asserting it.
    """
    forged_header = b"\x01" + (3).to_bytes(8, "big") + b"abc"
    sneaky = _sample(params_json=forged_header, decision=None)
    honest = _sample(params_json=b"", decision="abc")
    assert row_hash(sneaky) != row_hash(honest)
    assert _from_the_document(sneaky) != _from_the_document(honest)


def test_vector_one_byte_perturbation() -> None:
    """Changing a single byte of any field changes the digest."""
    base = _sample()
    baseline = row_hash(base)
    for name in FIELD_ORDER:
        value = base[name]
        if isinstance(value, str) and value:
            changed = dict(base)
            changed[name] = value[:-1] + chr(ord(value[-1]) ^ 1)
            assert row_hash(changed) != baseline, f"a one-byte change in {name} did not move it"


def test_the_magic_separates_this_preimage_from_any_other() -> None:
    """Without it, a row preimage could be presented as some other structure's bytes."""
    values = _sample()
    assert preimage(values).startswith(b"onedoor/row-preimage/1")
    assert hashlib.sha256(preimage(values)).hexdigest() == row_hash(values)


# --- Coverage of the schema, so a new column cannot slip outside the hash ---------


def test_every_column_is_either_hashed_or_deliberately_excluded(conn: Connection) -> None:
    """A migration that adds a column fails here until someone classifies it.

    A column that silently fell outside the preimage would be a field an attacker
    could edit without breaking the chain, and it would look complete in review: the
    schema would carry it and the hash would not.
    """
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(actions_audit)")}
    classified = set(FIELD_ORDER) | set(EXCLUDED)
    unclassified = columns - classified
    assert not unclassified, (
        f"columns neither hashed nor excluded: {sorted(unclassified)}. Add them to "
        f"FIELD_ORDER (a new preimage version) or to EXCLUDED with the reason."
    )
    stale = classified - columns
    assert not stale, f"the preimage names columns the table does not have: {sorted(stale)}"


def test_the_document_and_the_module_exclude_the_same_columns() -> None:
    """§4's table and `EXCLUDED` must name the same columns, with reasons.

    The first cut of this test asserted each reason was longer than twenty characters
    and failed on `row_hash: "it is the output"` -- which is the clearest reason in the
    table. Measuring prose length is not a rule; it is a proxy that punishes the good
    case. What actually matters is that the normative document and the code exclude the
    same set, so a column cannot be dropped from the hash in one place and left in the
    other.
    """
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("## 4. What is excluded", 1)[1].split("## 5.", 1)[0]
    documented = {
        name
        for row in re.finditer(r"^\| *`([^|]+)` *\| *([^|]+)\|", section, re.M)
        for name in (n.strip(" `") for n in row.group(1).split(","))
    }
    assert documented == set(EXCLUDED), (
        f"docs/row-preimage.md §4 and preimage.EXCLUDED disagree: {documented ^ set(EXCLUDED)}"
    )
    for column, reason in EXCLUDED.items():
        assert reason.strip(), f"{column} is excluded without a stated reason"


def test_a_missing_field_raises_rather_than_hashing_a_partial_row() -> None:
    values = _sample()
    del values["outcome"]
    with pytest.raises(KeyError, match="missing declared fields"):
        preimage(values)


def test_an_undeclared_column_type_raises(conn: Connection) -> None:
    """Every column must have a declared byte form; a new type is a spec change."""
    values = _sample(detail=Decimal("1.5"))
    with pytest.raises(TypeError, match="declared byte form"):
        preimage(values)


# --- Against real rows the engine wrote ------------------------------------------


def test_the_preimage_reads_a_real_audit_row(conn: Connection, config: EngineConfig) -> None:
    """The columns named in §3 are the columns the engine actually writes."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("10")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    result = decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("99")}, cost_eur=Decimal("99")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    row = conn.execute(
        "SELECT * FROM actions_audit WHERE id=?",
        (result.audit_id,),  # type: ignore[union-attr]
    ).fetchone()
    values = {name: row[name] for name in FIELD_ORDER}
    assert _from_the_document(values) == preimage(values)
    assert len(row_hash(values)) == 64


# --- R032 §2: one normative source, guarded rather than promised ------------------

PREIMAGE_BUILDERS = {"preimage.py"}
"""The only module in `onedoor/` permitted to construct row-preimage bytes.

R032 §2 ratified `docs/row-preimage.md` as the single normative source that `ND-015`
and `ND-017` **cite and never re-derive**. A promise in a document is not a guard, and
the whole reason the rule exists is that two derivations of one preimage disagree
eventually — at the exact spot an attacker would shop for a disagreement (X-14).
"""


def test_only_one_module_builds_preimage_bytes() -> None:
    """`sig` and the `E` digest must import this, not grow their own.

    Checked with an AST for the same reason the viewer's guard is: a comment mentioning
    `MAGIC` is not a use of it, and a test that cannot tell the difference gets deleted
    by the first person it annoys.
    """
    import ast

    package = Path(__file__).resolve().parents[2] / "onedoor"
    offenders: dict[str, list[str]] = {}
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts or "_vendor" in path.parts:
            continue
        if path.name in PREIMAGE_BUILDERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Detected by IMPORT, not by name. `ABSENT` and `PRESENT` are ordinary English
        # words and the first version of this test fired on `Status.ABSENT` in
        # `receipt.py` -- the third time a blunt name scan has flagged correct code in
        # this repo. Importing the FRAMING PRIMITIVES is the precise signal: you cannot
        # build preimage bytes without them, and calling `row_hash` needs none of them.
        framing = {"MAGIC", "ABSENT", "PRESENT", "encode_field", "LENGTH_BYTES"}
        found = [
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "onedoor.guardrail.preimage"
            for alias in node.names
            if alias.name in framing
        ]
        # Constructing the bytes is the offence; CALLING `row_hash`/`row_hash_of` is
        # exactly what every caller is supposed to do.
        if found:
            offenders[path.name] = sorted(set(found))
    assert not offenders, (
        f"modules building preimage bytes outside preimage.py: {offenders}. "
        f"docs/row-preimage.md is the single normative source (R032 §2): cite it, "
        f"call `row_hash`, never re-derive."
    )


def test_the_document_declares_itself_normative_and_names_its_dependants() -> None:
    """The rule has to be findable by the person who would otherwise break it.

    Someone implementing `ND-015` reads the spec, not this test. If the document does
    not say "cite, never re-derive", the guard above is a trap rather than a rule.
    """
    text = SPEC.read_text(encoding="utf-8")
    assert "single normative source" in text.lower()
    assert "ND-015" in text and "ND-017" in text
    assert "never re-derive" in text


def test_the_spec_carries_no_control_bytes() -> None:
    """A normative document is read by machines as well as people.

    Not hypothetical: an editing pass writing this file interpreted `\x00` and wrote
    literal NUL and SOH bytes into the prose describing those very tags. It rendered as
    two empty backticks and would have been invisible in review, in the one document
    whose job is to be reproducible from its text.
    """
    raw = SPEC.read_bytes()
    control = {b for b in raw if b < 0x09 or 0x0B <= b <= 0x1F}
    assert not control, f"control bytes in the normative spec: {sorted(control)}"
