"""Bound permits: a signed, per-request decision carried across a trust boundary.

Standalone by design: nothing here imports the engine (`onedoor.guardrail`), the
store (`onedoor.store`) or the service (`onedoor.service`). A recipient enforcement
point that never runs onedoor's own decision engine can still verify a permit issued
by one, using only this package. See "bound-permit profile" (cited by section
number in docstrings throughout) and AADP for the concepts this package implements.
"""

from __future__ import annotations
