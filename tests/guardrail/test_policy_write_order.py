"""The two policy-set write orders, pinned because a ruling now rests on them.

**This is load-bearing knowledge, not trivia** (R054 acknowledgment, on `ND-053` §6a).

The two paths that write a whole policy set write it in **opposite orders**:

```
policy_loader.load_file : POLICIES first, then effect policies
ratify._apply           : EFFECT POLICIES first, then policies
```

That asymmetry is *evidence in a ruling*. It is why a connection-reading inert-effect
check inside `upsert` is wrong rather than merely inelegant: during `load_file` no effect
policy has been written yet when each rule is upserted, so such a check would refuse every
valid file at boot — while the same set, written through the ceremony, would pass. **The
same rules would get different verdicts depending on which path wrote them.**

**Why this is a test rather than a comment.** Someone harmonising the two orders in a
future cleanup would be doing something defensible — and would *silently invalidate the
analysis behind a recorded ruling* without failing anything. This makes that loud. It does
not forbid the change; it requires whoever makes it to go back to `ND-053` §6a and re-run
the reasoning, because if both paths write effects first then option (a) becomes viable
and the parked lean needs revisiting.

Nothing here asserts that either order is *better*. It asserts only that they currently
differ, and that the difference is being relied upon.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from onedoor.guardrail import policy_loader
from onedoor.studio import ratify


def _write_order(func: object) -> list[str]:
    """Which of `upsert` / `upsert_effect` this function calls, in source order.

    Read from the AST rather than by string search: `"upsert(conn"` also matches inside
    `upsert_effect(conn`, and a substring that matches its own sibling is the
    proxy-for-contract class this repository has paid for six times.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))  # type: ignore[arg-type]
    calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else None
        )
        if name in {"upsert", "upsert_effect"}:
            calls.append((node.lineno, name))
    # Deduplicate to first appearance, preserving source order.
    seen: list[str] = []
    for _, name in sorted(calls):
        if name not in seen:
            seen.append(name)
    return seen


def test_load_file_writes_policies_before_effect_policies() -> None:
    order = _write_order(policy_loader.load_file)
    assert order == ["upsert", "upsert_effect"], (
        f"`load_file`'s write order changed to {order}. That is not forbidden — but a "
        "recorded ruling rests on it (ND-053 §6a): during `load_file` no effect policy "
        "exists yet when a rule is upserted, which is why a per-row connection check is "
        "wrong. If this order changed, go re-run that analysis before trusting it."
    )


def test_the_ceremony_writes_effect_policies_before_policies() -> None:
    order = _write_order(ratify._apply)
    assert order == ["upsert_effect", "upsert"], (
        f"the ceremony's write order changed to {order}. See ND-053 §6a — the asymmetry "
        "between this and `load_file` is the evidence that killed option (a)."
    )


def test_the_two_orders_are_still_opposite() -> None:
    """The asymmetry itself, asserted directly rather than inferred from the two above.

    Stated as its own fact because *this* is what the ruling uses. If the two tests above
    were ever relaxed independently, this is the one that still notices the property they
    were protecting has gone.
    """
    loader = _write_order(policy_loader.load_file)
    ceremony = _write_order(ratify._apply)
    assert loader == list(reversed(ceremony)), (
        f"the two set-writing paths no longer disagree: load_file={loader}, "
        f"ceremony={ceremony}. ND-053 §6a's argument against a per-row connection check "
        "depends on them differing. Harmonising them may well be an improvement — but it "
        "changes what is provable, so the ruling's evidence must be re-derived rather "
        "than assumed to survive."
    )


def test_both_paths_write_both_kinds() -> None:
    """A guard whose search space is empty passes for the wrong reason."""
    assert set(_write_order(policy_loader.load_file)) == {"upsert", "upsert_effect"}
    assert set(_write_order(ratify._apply)) == {"upsert", "upsert_effect"}
