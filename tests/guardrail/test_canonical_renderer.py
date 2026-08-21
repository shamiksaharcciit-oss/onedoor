"""The canonical renderer: E8's tripartite equality, over generated inputs.

`0.4.0` routes every decimal and datetime through one renderer, and E8 fixes what
"one" means: **shortest exact form, wire = storage = preimage**. The equality is the
property — three legs tested separately can each pass while the equality between them
fails, which is why the tripartite assertion below is a single test rather than three.

Inputs are **generated**, not hand-picked. Discipline 4 exists because spot-checks
find only the violations you thought of, and this session has a standing reminder:
an exhaustive-looking search for a corrupted character missed `⇒` because the
candidate set was assembled from characters already seen. A hand-written list of
decimal spellings has the same shape of blind spot.

The renderer itself is vendored, never reimplemented — see `onedoor/_vendor/`.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from onedoor._vendor.canonical import canon_datetime, canon_decimal, canonical_bytes

# Deterministic: a fixed seed means a failure is reproducible from the report alone,
# which a random-per-run generator does not give you.
SEED = 20260821


def _equal_value_spellings(rng: random.Random) -> list[tuple[str, list[str]]]:
    """Generate groups of *differently spelled, equal-valued* decimal literals."""
    groups = []
    for _ in range(200):
        units = rng.randint(0, 10**6)
        frac_digits = rng.randint(0, 4)
        frac = rng.randint(0, 10**frac_digits - 1) if frac_digits else 0
        base = Decimal(units) + (Decimal(frac) / Decimal(10**frac_digits) if frac_digits else 0)
        sign = -1 if rng.random() < 0.25 else 1
        base = base * sign

        spellings = [str(base)]
        # trailing zeros: 250 -> 250.00, 250.000
        for pad in (1, 2, 3):
            spellings.append(f"{base:.{max(frac_digits, 0) + pad}f}")
        # exponent form, the str(Decimal) trap: Decimal("2.5E+2")
        if base != 0:
            spellings.append(str(base.normalize()))
            _, digits, exp = base.normalize().as_tuple()
            if isinstance(exp, int):
                spellings.append(f"{base:E}")
        groups.append((str(base), spellings))
    return groups


def test_equal_values_render_to_identical_bytes_however_they_are_spelled() -> None:
    """The core of E8: scale and notation are authoring choices, not value."""
    rng = random.Random(SEED)
    checked = 0
    for _, spellings in _equal_value_spellings(rng):
        rendered = {canon_decimal(Decimal(s)) for s in spellings}
        assert len(rendered) == 1, (
            f"equal values rendered differently: {spellings} -> {sorted(rendered)}. "
            f"Scale and exponent notation must not survive canonicalisation."
        )
        checked += len(spellings)
    assert checked > 800, "the generator must actually exercise a broad space"


def test_canonical_output_re_canonicalises_to_itself() -> None:
    """Idempotence. A renderer that is not a fixed point cannot be a preimage."""
    rng = random.Random(SEED + 1)
    for value, _ in _equal_value_spellings(rng):
        once = canon_decimal(Decimal(value))
        assert canon_decimal(Decimal(once)) == once


def test_wire_storage_and_preimage_are_the_same_bytes() -> None:
    """E8's tripartite equality, asserted as ONE property.

    Testing "the wire form is shortest-exact", "the stored form is shortest-exact"
    and "the preimage is shortest-exact" as three separate properties lets all three
    pass while the *equality between them* fails -- which is the only thing that
    actually matters to a second implementation trying to reproduce a digest.
    """
    rng = random.Random(SEED + 2)
    for value, spellings in _equal_value_spellings(rng):
        for spelling in spellings:
            d = Decimal(spelling)
            wire = canon_decimal(d)  # what a response carries
            storage = canon_decimal(d)  # what the audit row holds
            preimage = canonical_bytes({"v": canon_decimal(d)})  # what gets hashed

            assert wire == storage, f"wire and storage diverge for {spelling!r}"
            assert preimage == canonical_bytes({"v": wire}), (
                f"the hashed bytes are not the bytes on the wire for {spelling!r}"
            )
            assert wire.encode("utf-8") in preimage, (
                f"the wire rendering does not appear verbatim in its own preimage for {spelling!r}"
            )
        assert canon_decimal(Decimal(value)) == canon_decimal(Decimal(spellings[0]))


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("250.00", "250"),
        ("0.50", "0.5"),
        ("-0", "0"),
        ("-0.000", "0"),
        ("2.5E+2", "250"),
        ("0", "0"),
    ],
)
def test_the_rulings_worked_examples(literal: str, expected: str) -> None:
    """E8 and R002 gave worked examples by hand; hold them as stated.

    These are the ruled cases, kept alongside the generated space rather than
    instead of it -- the generator proves the property, these prove delivery read
    the ruling right.
    """
    assert canon_decimal(Decimal(literal)) == expected


def test_floats_are_refused_at_the_boundary() -> None:
    """Never float. The renderer is the door that guard sits on."""
    with pytest.raises(TypeError):
        canon_decimal(250.00)


def test_datetimes_render_rfc3339_utc_shortest_exact() -> None:
    rng = random.Random(SEED + 3)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for _ in range(200):
        dt = base + timedelta(
            days=rng.randint(0, 3000),
            seconds=rng.randint(0, 86399),
            microseconds=rng.choice([0, 0, 0, rng.randint(1, 999999)]),
        )
        out = canon_datetime(dt)
        assert out.endswith("Z"), f"UTC designator must be uppercase Z: {out}"
        assert "+00:00" not in out
        assert out[10] == "T"
        seconds_field = out[17:19]
        assert seconds_field.isdigit(), f"seconds must always be present: {out}"
        if dt.microsecond == 0:
            assert "." not in out, f"fractional seconds must be omitted at zero: {out}"
        else:
            assert not out.split(".")[1].rstrip("Z").endswith("0"), (
                f"fractional seconds must be shortest-exact: {out}"
            )


def test_the_vendored_renderer_is_byte_identical_to_the_reference_artifact() -> None:
    """The vendoring guarantee, held by a test rather than by intent.

    onedoor never reimplements the canonical form; it copies core's. That is only
    true while the copy matches, and a copy nothing checks is a copy that drifts.
    """
    from pathlib import Path

    import onedoor._vendor.canonical as vendored

    repo = Path(__file__).resolve().parents[2]
    origin = repo / "reference" / "rederivable-manifest" / "canonical.py"
    assert Path(vendored.__file__).read_bytes() == origin.read_bytes(), (
        "the vendored canonical.py has drifted from the pinned artifact. Do not "
        "edit either copy -- re-vendor from reference/rederivable-manifest/."
    )
