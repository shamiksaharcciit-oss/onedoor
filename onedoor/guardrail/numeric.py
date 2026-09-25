"""One answer to "is this a number?" — ND-054 / F-B.

Before this module two paths answered that question separately: ``bounds.validate`` and
``caps.resolve_cost``. They disagreed about the decimal-string form, so **declaring a
numeric bound changed which wire types an action accepted** — the draft's own worked
example (`"amount_eur": "40.00"`) was read as money by one path and refused by the
other. Two implementations of one question is X-14, and here it sat on the
arithmetical entrance to the evaluation path.

The ruling (ND-054 §4): **one ``numeric_value(raw)``, called by both**, with a test
asserting they cannot answer differently. That clause is the fix; accepting decimal
strings is what it makes true in both places at once.

Readings, stated rather than implied:

- **Never through ``float``.** A ``str`` is parsed by ``Decimal`` directly. The draft's
  rule is *evaluated exactly*, and routing a received amount through a binary double to
  check a bound would reintroduce at the check the hazard the rule keeps away from the
  caller.
- **A ``float`` parameter is converted through ``str``** — Python's shortest
  round-tripping rendering, i.e. the decimal value the caller wrote. That is what
  ``resolve_cost`` already did, so money accounting is unchanged; it is ``bounds`` that
  moves into line, and only on the in-process binding, where a caller hands Python
  objects over rather than bytes (JSON ingress produces no floats).
- **The accepted string form is plain fixed-point** (`"12.50"`, `"-0.5"`, `"12"`).
  Exponent notation is refused: `Decimal("1e400")` would be finite and would compare,
  so that refusal is a decision about the accepted *spelling* (WO-D1 step 1 names
  `"1e400"` as a must-refuse case). The canonical renderer (`canon_decimal`) does
  *not* refuse exponent notation on input — it accepts it and normalises to
  fixed-point on output — so it is not authority for refusing it here; this module
  simply never emits the exponent form it declines to accept.
- **Non-finite spellings are refused for a different reason than garbage**
  (``NOT_FINITE``, not ``NOT_NUMERIC``). E10 rules NaN and Infinity malformed input
  rather than "not numeric", and the messages below keep that distinction legible.
- **``bool`` is refused.** It is an ``int`` subclass, and both paths already excluded it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal

NOT_NUMERIC = "not_numeric"
"""The value is not a number in any accepted form."""

NOT_FINITE = "not_finite"
"""The value names a non-finite number (NaN/Infinity) — malformed, not garbled (E10)."""

_PLAIN_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
"""A plain fixed-point decimal string: optional sign, digits, optional fraction.

No exponent, no thousands separator, no underscore digit grouping — those are spellings
Decimal accepts and this path deliberately does not.
"""

_NON_FINITE_SPELLINGS = frozenset(
    {"nan", "snan", "-nan", "+nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
)
"""What `Decimal` reads as a non-finite value, lowercased.

Named rather than probed so the refusal reason does not depend on Decimal's parsing
quirks: `Decimal("sNaN")` raises, `Decimal("NaN")` does not, and the caller must get the
same stated reason either way.
"""


@dataclass(frozen=True)
class NumericParse:
    """One question, one answer — with the reason attached when the answer is no.

    ``value is None`` iff ``reason is not None``: the two are set together, so no caller
    can observe a refusal without being able to say what it refused.
    """

    value: Decimal | None
    reason: str | None


def parse_numeric(raw: object) -> NumericParse:
    """Decide whether ``raw`` is a number, and say why not when it is not.

    The single implementation. :func:`numeric_value` and :func:`numeric_refusal` are its
    two faces, so neither can drift from the other (X-14).
    """
    if isinstance(raw, bool):  # before int: bool IS an int subclass
        return NumericParse(None, NOT_NUMERIC)
    if isinstance(raw, int):
        return NumericParse(Decimal(raw), None)
    if isinstance(raw, Decimal):
        return NumericParse(raw, None) if raw.is_finite() else NumericParse(None, NOT_FINITE)
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return NumericParse(None, NOT_FINITE)
        return NumericParse(Decimal(str(raw)), None)
    if not isinstance(raw, str):
        return NumericParse(None, NOT_NUMERIC)
    text = raw.strip()
    if text.lower() in _NON_FINITE_SPELLINGS:
        return NumericParse(None, NOT_FINITE)
    if _PLAIN_DECIMAL.fullmatch(text) is None:
        return NumericParse(None, NOT_NUMERIC)
    return NumericParse(Decimal(text), None)


def numeric_value(raw: object) -> Decimal | None:
    """``raw`` as an exact :class:`Decimal`, or None when it is not a number.

    The one function `bounds` and `resolve_cost` both call. None means "not a usable
    number", never zero: a bound that cannot read its parameter is a denial, not an
    admission.
    """
    return parse_numeric(raw).value


def numeric_refusal(name: str, raw: object) -> str:
    """The stated reason `raw` was refused as ``name``, for a denial the operator reads.

    The parameter is named because a denial that does not say *which* parameter failed
    is the kind of message that makes an operator re-read the whole request.
    """
    reason = parse_numeric(raw).reason
    if reason == NOT_FINITE:
        return f"param '{name}'={raw!r} is not a finite number"
    return (
        f"param '{name}' must be numeric: an int, a finite Decimal, or a decimal "
        f'string such as "12.50" (got {raw!r})'
    )
