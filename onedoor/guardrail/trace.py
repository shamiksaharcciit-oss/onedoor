"""The evaluation trace: the ordered list of checks a verdict was actually made from
(WO-D1 step 5, AADP -03 §10, a MUST).

A check that the pipeline never reached must never appear in the trace -- least of
all as `pass`. This module gives :mod:`decision` exactly one way to grow a trace: an
append-only builder, filled in the same order the pipeline evaluates checks, never
retroactively. That is what makes "the verdict's reason must be checkable from the
trace alone" true by construction rather than by promise -- the last `fail` entry
recorded is, by construction, the one whose escalation the returned decision reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from onedoor._vendor.canonical import canon_decimal

TraceResult = Literal["pass", "fail", "unresolved"]


def _stringify(value: object) -> str:
    """A trace value is always a string -- the value/bound/state a check read.

    `Decimal` renders through the canonical form so a money bound reads the same way
    it would anywhere else onedoor shows one; `None` reads as the literal `"none"`
    rather than Python's `str(None)` accident, since a trace is evidence read by a
    human or another system, never re-parsed back into Python.
    """
    if isinstance(value, Decimal):
        return canon_decimal(value)
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass(frozen=True)
class TraceEntry:
    check: str
    rule: str
    condition: str
    value: str
    result: TraceResult

    def to_dict(self) -> dict[str, str]:
        return {
            "check": self.check,
            "rule": self.rule,
            "condition": self.condition,
            "value": self.value,
            "result": self.result,
        }


@dataclass
class Trace:
    """An ordered, append-only record of one decision's evaluated checks.

    No method removes or reorders an entry: the only way an entry stops mattering is
    that the caller returns before adding the next one, which is exactly the
    "short-circuited pipeline shows no entries after the point where it stopped"
    requirement -- it falls out of building the trace inline with the pipeline rather
    than computing it afterward from the final decision.
    """

    entries: list[TraceEntry] = field(default_factory=list)

    def add(
        self, check: str, rule: str, condition: str, value: object, result: TraceResult
    ) -> None:
        self.entries.append(TraceEntry(check, rule, condition, _stringify(value), result))

    def to_json(self) -> str:
        import json

        return json.dumps([e.to_dict() for e in self.entries], separators=(",", ":"))

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def failing(self) -> TraceEntry | None:
        """The last `fail` entry, if any -- the one a deny/confirm reason must match.

        Last, not first: later checks can supersede an earlier escalation (an opaque
        host invariant can override an effect-floor reason for the same request), and
        the pipeline's own reason_code assignment follows the identical last-write-wins
        rule, in the identical order. Matching that order is what keeps this function
        honest rather than merely convenient.
        """
        for entry in reversed(self.entries):
            if entry.result == "fail":
                return entry
        return None
