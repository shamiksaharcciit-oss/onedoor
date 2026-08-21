"""Make the LiteLLM example importable without installing LiteLLM.

`litellm` is a heavy dependency and is not in `[dev]`, so CI does not have it.
The alternative to a stand-in is skipping these tests on CI — and a skipped test
is the one thing this suite must not ship: a gate that never fires is
indistinguishable from a gate that passes (R010 §1, and the whole reason
`ND-025`'s Tests step hid a broken suite for weeks).

What the stand-in costs, stated plainly: these tests exercise **onedoor's** half
of the contract — that no result is reported before the act, that exactly one is
reported after it, and that each call reports against its own permit. They do not
exercise LiteLLM's dispatch. The hook signatures they call were read from litellm
1.97.0's `CustomLogger` rather than guessed, and the argument order differs
between the three hooks, which is worth knowing before editing them.

When LiteLLM *is* installed, the real base class is used and the stand-in is
never built.
"""

from __future__ import annotations

import sys
import types
from typing import Any

try:  # pragma: no cover - depends on the environment, both branches are correct
    import litellm.integrations.custom_guardrail  # noqa: F401
except Exception:  # noqa: BLE001 - any import failure means "use the stand-in"

    class CustomGuardrail:  # minimal stand-in: the example only subclasses it
        def __init__(self, **kwargs: Any) -> None:
            self.guardrail_name = kwargs.get("guardrail_name")

    _litellm = types.ModuleType("litellm")
    _integrations = types.ModuleType("litellm.integrations")
    _custom_guardrail = types.ModuleType("litellm.integrations.custom_guardrail")
    _custom_guardrail.CustomGuardrail = CustomGuardrail  # type: ignore[attr-defined]
    _integrations.custom_guardrail = _custom_guardrail  # type: ignore[attr-defined]
    _litellm.integrations = _integrations  # type: ignore[attr-defined]
    sys.modules.setdefault("litellm", _litellm)
    sys.modules.setdefault("litellm.integrations", _integrations)
    sys.modules.setdefault("litellm.integrations.custom_guardrail", _custom_guardrail)
