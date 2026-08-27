"""T4 — the decision path cannot reach a proposer (ND-052 / S6, R053 §5).

**Built first, deliberately.** It is the test that keeps constitution principle 1 true
while everything else in S6 lands: *the proposer is never the enforcer.* A model must not
be reachable from the code that decides whether an action may happen — not by import, not
by a lazy import inside a function, not through three hops of convenience.

Structural rather than by inspection, in the shape of
`test_every_audit_write_path_stamps_the_chain`: it walks the **transitive import closure**
of the decision path from the package's own source, so a future module that reaches for a
proposer fails at the moment it is written rather than in whatever review notices it.

**Lazy imports count.** The closure is computed from every `import` statement in a file,
including ones nested inside functions, because `from onedoor.studio import proposer`
buried in a helper is exactly the shape this test exists to catch — it is invisible at
module scope and completely effective at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "onedoor"

DECISION_PATH_ROOTS = (
    "onedoor.guardrail.decision",
    "onedoor.guardrail.executor",
    "onedoor.guardrail.policy",
    "onedoor.guardrail.caps",
    "onedoor.guardrail.bounds",
    "onedoor.guardrail.killswitch",
)
"""What "the decision path" means, named rather than inferred.

Every module the engine consults while deciding whether an action may happen. Naming them
is the point: a test that guessed the boundary would move whenever the code did, and this
boundary is exactly what must not move.
"""

MODEL_CLIENTS = frozenset(
    {
        "openai",
        "anthropic",
        "litellm",
        "langchain",
        "langchain_core",
        "langgraph",
        "cohere",
        "mistralai",
        "google",
        "ollama",
        "transformers",
        "httpx",
        "requests",
        "urllib3",
    }
)
"""Model clients **and the HTTP libraries one would be reached through.**

Broader than "an LLM SDK" on purpose. The decision path is offline and deterministic; a
network client in its closure is a defect whether or not a model is on the other end,
because the property being protected is *this code does not call out*, not *this code does
not call a model specifically*.
"""


def _module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    """Every module imported anywhere in the file — including inside functions."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import: resolve against the file's own package
                package = _module_name(path).rsplit(".", node.level)[0]
                found.add(f"{package}.{node.module}" if node.module else package)
            elif node.module:
                found.add(node.module)
                # `from onedoor.studio import proposer` names the submodule in `names`,
                # not in `module`. Missing that is how this whole test would pass while
                # the import it exists to catch sat in plain sight.
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _source_of(module: str) -> Path | None:
    base = PACKAGE.parent / Path(*module.split("."))
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return None


def import_closure(roots: tuple[str, ...]) -> set[str]:
    """Every module transitively imported by `roots`, first-party and third-party alike."""
    seen: set[str] = set()
    queue = list(roots)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        source = _source_of(module)
        if source is None:  # third-party or stdlib: recorded, not walked
            continue
        for imported in _imports(source):
            if imported not in seen:
                queue.append(imported)
    return seen


@pytest.fixture(scope="module")
def closure() -> set[str]:
    return import_closure(DECISION_PATH_ROOTS)


def test_the_decision_path_cannot_reach_the_studio(closure: set[str]) -> None:
    """Principle 1, structurally: **the proposer is never the enforcer.**

    The Studio proposes; the engine decides. Not one module the engine consults while
    deciding may reach into the package that drafts policy — and `onedoor.studio.proposer`
    is the one that would eventually call a model.
    """
    studio = sorted(m for m in closure if m.startswith("onedoor.studio"))
    assert studio == [], (
        f"the decision path imports the Studio: {studio}. The proposer is never the "
        "enforcer — if the engine can reach the thing that drafts policy, principle 1 is "
        "false whatever the docstrings say."
    )


def test_the_decision_path_cannot_reach_a_model_client(closure: set[str]) -> None:
    """The engine is offline and deterministic. A network client in its closure ends that."""
    offenders = sorted(m for m in closure if m.split(".")[0] in MODEL_CLIENTS)
    assert offenders == [], (
        f"the decision path can reach a network or model client: {offenders}. The engine "
        "decides offline; anything it can call out through is a defect whether or not a "
        "model is on the other end."
    )


def test_the_closure_actually_walked_something(closure: set[str]) -> None:
    """A guard whose search space is empty passes for the wrong reason.

    If `DECISION_PATH_ROOTS` were renamed and `_source_of` quietly returned `None` for
    every one of them, the two tests above would pass while checking nothing. This asserts
    the closure is real before their result means anything.
    """
    assert "onedoor.guardrail.decision" in closure
    assert len(closure) > 15, f"the import closure is implausibly small: {sorted(closure)}"
    assert any(m.startswith("onedoor.guardrail") for m in closure)


def test_a_lazy_import_inside_a_function_is_caught(tmp_path: Path) -> None:
    """The shape the test exists for, proven rather than assumed.

    A `from onedoor.studio import proposer` buried in a helper is invisible at module
    scope and completely effective at runtime. `_imports` walks the whole AST, so it sees
    one — asserted here against a file written for the purpose, because the real decision
    path (correctly) contains no such import to detect.
    """
    sneaky = tmp_path / "sneaky.py"
    sneaky.write_text(
        "def helper():\n    from onedoor.studio import proposer\n    return proposer\n",
        encoding="utf-8",
    )
    found = _imports(sneaky)
    assert "onedoor.studio" in found
    assert "onedoor.studio.proposer" in found, (
        "a submodule imported via `from X import Y` was not seen — the closure would "
        "miss exactly the import this suite guards"
    )
