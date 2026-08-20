"""Optional OpenTelemetry wiring — no-ops cleanly when otel isn't installed.

Spans: ``onedoor.decide`` / ``onedoor.report`` with action type attributes.
Metrics: a decision counter keyed by outcome/reason/tier. The engine never
requires a collector; installing ``onedoor[otel]`` and configuring the standard
OTEL_* environment variables is all it takes to light up.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

try:  # pragma: no cover - exercised only when otel is installed
    from opentelemetry import metrics, trace

    _tracer = trace.get_tracer("onedoor")
    _meter = metrics.get_meter("onedoor")
    _decisions = _meter.create_counter(
        "onedoor.decisions", description="Guardrail decisions by outcome"
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
        s.set_attribute("onedoor.action_type", action_type)
        yield


def record_decision(action_type: str, outcome: str, reason: str, tier: int) -> None:
    if not _HAVE_OTEL:
        return
    _decisions.add(  # pragma: no cover
        1,
        {
            "onedoor.action_type": action_type,
            "onedoor.outcome": outcome,
            "onedoor.reason": reason,
            "onedoor.tier": str(tier),
        },
    )
