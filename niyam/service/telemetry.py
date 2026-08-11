"""Optional OpenTelemetry wiring — no-ops cleanly when otel isn't installed.

Spans: ``niyam.decide`` / ``niyam.report`` with action type attributes.
Metrics: a decision counter keyed by outcome/reason/tier. The engine never
requires a collector; installing ``niyam[otel]`` and configuring the standard
OTEL_* environment variables is all it takes to light up.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

try:  # pragma: no cover - exercised only when otel is installed
    from opentelemetry import metrics, trace

    _tracer = trace.get_tracer("niyam")
    _meter = metrics.get_meter("niyam")
    _decisions = _meter.create_counter(
        "niyam.decisions", description="Guardrail decisions by outcome"
    )
    _HAVE_OTEL = True
except Exception:  # pragma: no cover
    _HAVE_OTEL = False


@contextmanager
def span(name: str, action_type: str) -> Iterator[None]:
    if not _HAVE_OTEL:
        yield
        return
    with _tracer.start_as_current_span(name) as s:  # pragma: no cover
        s.set_attribute("niyam.action_type", action_type)
        yield


def record_decision(action_type: str, outcome: str, reason: str, tier: int) -> None:
    if not _HAVE_OTEL:
        return
    _decisions.add(  # pragma: no cover
        1,
        {
            "niyam.action_type": action_type,
            "niyam.outcome": outcome,
            "niyam.reason": reason,
            "niyam.tier": str(tier),
        },
    )
