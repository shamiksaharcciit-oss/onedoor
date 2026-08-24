"""Every third-party module `onedoor` imports must be installed by `[dev]` (R010's shape).

Why this test exists, and the defect that produced it
-------------------------------------------------------
S3 added `import uvicorn` inside `studio.server.serve`. `mypy onedoor` passed locally
and **CI went red on both jobs** with *"Cannot find implementation or library stub for
module named uvicorn"*. The gate's own command had been run verbatim — the failure was
one layer under that: the local virtualenv happened to have uvicorn, and `[dev]`, which
is all CI installs, did not.

So this is R010's rule with a new edge. *A verification claim about a gate must come
from the gate's own commands* — and the command is only half of a gate. **The other half
is the environment it runs in, and a local environment drifts richer than CI's simply by
being used.** Running the right command in the wrong world is a green answer about a
different machine.

The fix is not to make mypy check less. An `ignore_missing_imports` override would have
turned CI green by silencing the one call site the dependency exists for, which is the
wrong direction: `cryptography` is in `[dev]` for exactly this reason, so the guarded
signing path is really type-checked rather than waved through. `uvicorn` joined it.

This test closes the class **locally, at the moment an import is written**, so the next
one does not need a red CI run to be found. Structural, not a checklist: it reads the
package's own ASTs and resolves each third-party module to its installed distribution.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "onedoor"
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

DECLARED_ELSEWHERE = {
    "opentelemetry": (
        "the [otel] extra, with a `tool.mypy.overrides` entry setting "
        "`ignore_missing_imports`. Declared here so the exception stays ONE exception "
        "rather than becoming the habit: OpenTelemetry ships no stubs mypy can use, so "
        "installing it would not buy the checking that installing `cryptography` and "
        "`uvicorn` does."
    ),
}
"""Modules deliberately absent from `[dev]`, each with the reason it is absent.

A dict rather than a set: an exception without a written reason is indistinguishable
from an oversight six months later.
"""


def _third_party_imports() -> set[str]:
    """Top-level module names imported anywhere in the package, minus stdlib and self.

    `_vendor` is skipped: vendored code is **received data** whose imports are the
    upstream author's, not this project's, and rewriting them to suit our extras would
    be exactly the byte-rewriting E10 fences against.
    """
    modules: set[str] = set()
    for source in PACKAGE.rglob("*.py"):
        if "_vendor" in source.parts:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return {m for m in modules if m not in sys.stdlib_module_names and m != "onedoor"}


def _declared_distributions() -> set[str]:
    """Distribution names in `[project.dependencies]` and the `[dev]` extra, normalised."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    requirements = list(project.get("dependencies", []))
    requirements += list(project["optional-dependencies"]["dev"])
    names = set()
    for requirement in requirements:
        name = requirement.split(";")[0].strip()
        for separator in (">=", "==", "<=", "~=", "!=", "<", ">", "["):
            name = name.split(separator)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def test_every_third_party_import_is_declared_in_dev() -> None:
    """CI installs `.[dev]` and nothing else — so `[dev]` is what the gates can see.

    An import missing from here fails `mypy onedoor` in CI while passing on any
    developer machine that happens to have the package for another reason. That is a
    green answer about a different machine, and it is the failure this test converts
    into a local one.
    """
    resolvable = packages_distributions()
    declared = _declared_distributions()
    undeclared: dict[str, str] = {}
    for module in sorted(_third_party_imports()):
        if module in DECLARED_ELSEWHERE:
            continue
        distributions = resolvable.get(module)
        if not distributions:
            undeclared[module] = "not installed at all, so no gate can check it"
            continue
        if not any(d.lower().replace("_", "-") in declared for d in distributions):
            undeclared[module] = f"installed as {distributions} but absent from [dev]"
    assert not undeclared, (
        "onedoor imports modules the CI environment does not install: "
        f"{undeclared}. Add them to [dev] rather than silencing mypy — an "
        "`ignore_missing_imports` override makes the gate green by making it check "
        "less, which is the wrong direction."
    )


def test_the_studio_extra_exists_and_is_separate_from_service() -> None:
    """R047 §1 made them separate PROCESSES; sharing an extra would re-couple them.

    Not cosmetic: `onedoor.service` is the PDP, and the reason the Studio is its own
    process is that one credential must not both answer decisions and rewrite the rules.
    An operator installing `onedoor[service]` should not thereby install a policy editor.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert "studio" in extras, "the [studio] extra is gone"
    assert "service" in extras
    assert extras["studio"] is not extras["service"]


def test_every_exception_carries_its_reason() -> None:
    """An exception without a written reason is indistinguishable from an oversight."""
    for module, reason in DECLARED_ELSEWHERE.items():
        assert len(reason) > 40, f"{module} is excepted without a stated reason"
