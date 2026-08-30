"""`ND-056` / T1 — the staged validator's order is the loader's order, asserted structurally.

`staging.STAGES` is a claim about `policy_loader.load_file`: *these functions, in this
order, are what happens at boot.* A claim about code is a test, not a comment — and this
one has already earned its keep.

**It found the defect it exists to find, before it had run once.** `staging` first
ordered the stages `load → schema → effects → rules`, on the reasonable-sounding
assumption that a candidate is built before it is judged. `load_file` does the opposite:
*"validate all first"*, then construct the effect policies. A candidate carrying both a
bad effect tier and a tier-2 rule with no reversal would have been reported as stopping
at `effects` while the engine stops at `rules` — a stage name naming the wrong stage,
which is the loader's behaviour misdescribed by the screen whose entire purpose is to
describe it.

Walking the AST rather than the source text, for the reason V7 learned the hard way: a
checker that reads prose punishes code for explaining itself. This module's own docstring
names every one of these functions, and a substring check over the file would match the
documentation instead of the calls.
"""

from __future__ import annotations

import ast
import inspect

from onedoor.guardrail import policy_loader
from onedoor.studio import staging

STAGE_FUNCTIONS = {
    staging.STAGE_LOAD: "_safe_load_decimal",
    staging.STAGE_SCHEMA: "_policy_from_entry",
    staging.STAGE_RULES: "validate_policy",
    staging.STAGE_EFFECTS: "EffectPolicy",
}
"""The engine function each stage is a wrapper over. One name per stage, and the mapping
is asserted total below so a new stage cannot arrive undocumented."""


def _called_names(func: object) -> list[str]:
    """Every callee name in `func`, in source order, from the parsed tree."""
    tree = ast.parse(inspect.getsource(func))  # type: ignore[arg-type]
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            name = (
                target.id
                if isinstance(target, ast.Name)
                else target.attr
                if isinstance(target, ast.Attribute)
                else None
            )
            if name is not None:
                out.append((node.lineno, name))  # type: ignore[arg-type]
    return [name for _, name in sorted(out)]  # type: ignore[misc]


def test_every_stage_names_the_engine_function_it_wraps() -> None:
    assert tuple(STAGE_FUNCTIONS) == staging.STAGES, (
        "a stage exists with no engine function recorded for it -- the mapping must stay "
        "total, or a stage can be added that wraps nothing"
    )


def test_the_stage_order_is_the_order_load_file_calls_them() -> None:
    """The fence. `load_file`'s own call order decides `staging.STAGES`."""
    called = _called_names(policy_loader.load_file)
    positions = {}
    for stage, name in STAGE_FUNCTIONS.items():
        assert name in called, (
            f"`load_file` no longer calls {name!r}, which stage {stage!r} claims to wrap. "
            "The boot path changed; staging.STAGES must be re-derived from it."
        )
        positions[stage] = called.index(name)

    ordered = tuple(sorted(positions, key=lambda s: positions[s]))
    assert ordered == staging.STAGES, (
        f"staging.STAGES is {staging.STAGES} but `load_file` calls them in the order "
        f"{ordered}. The stage a candidate is reported against would name the wrong "
        "stage for any candidate that fails in two of them."
    )


def test_the_fence_can_fail() -> None:
    """Sabotage: a checker that has never been shown a lie has never been shown to look.

    The assertion above is only worth having if a wrong order would break it, so prove
    that a permuted order does — against the real call positions, not a mock.
    """
    called = _called_names(policy_loader.load_file)
    positions = [called.index(name) for name in STAGE_FUNCTIONS.values()]
    assert positions == sorted(positions), "precondition: the recorded order is the real one"

    wrong = (staging.STAGE_LOAD, staging.STAGE_SCHEMA, staging.STAGE_EFFECTS, staging.STAGE_RULES)
    assert wrong != staging.STAGES, "the permutation must differ, or this proves nothing"
    ordered = tuple(sorted(STAGE_FUNCTIONS, key=lambda s: called.index(STAGE_FUNCTIONS[s])))
    assert ordered != wrong, (
        "the effects-before-rules order -- the one this module originally shipped -- must "
        "not match what load_file does, or the fence would have passed on the defect"
    )


def test_staging_calls_the_engines_functions_and_defines_no_rules_of_its_own() -> None:
    """The second-validator fence: every refusal comes from an engine call.

    `staging` may raise `ValueError` for its own `Position` invariants, but it must not
    contain a policy rule -- no tier comparison, no `compensating_command` check, no
    `bounds.required` membership test. Those belong to `validate_policy` alone.
    """
    source = inspect.getsource(staging)
    tree = ast.parse(source)
    body = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    text = "\n".join(ast.unparse(node) for node in body)
    for forbidden in ("compensating_command", "cost_param", "Tier.AUTO", "bounds.required"):
        assert forbidden not in text, (
            f"{forbidden!r} appears in staging's executable code. A policy rule stated "
            "here is a second implementation of validate_policy, and the two disagree in "
            "the direction that lets a bad rule through."
        )
