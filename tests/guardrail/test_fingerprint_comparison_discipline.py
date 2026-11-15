"""Two sites compare a caller's principal against a stored keyed fingerprint
to decide whether a reference or a report may be honoured: `approval_ref.
resolve`'s binding, and `/v1/report`'s decide-key scoping. Neither behaviour
difference nor a sabotage can prove `hmac.compare_digest` is doing the
comparing rather than a plain `==`/`!=` -- a non-constant-time comparison
reaches the identical verdict on every input a test can construct, and the
timing channel it would leave open is not something a unit test's clock can
observe. This reads the actual source instead.
"""

from __future__ import annotations

import ast
import inspect

from onedoor.guardrail import approval_ref, approvals
from onedoor.service import app as app_module


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no function named {name!r} found in the parsed source")


def _check(func_node: ast.AST) -> tuple[bool, list[str]]:
    """(uses hmac.compare_digest, bare ==/!= comparisons naming a principal)."""
    uses_compare_digest = False
    bare_hits: list[str] = []
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compare_digest"
        ):
            uses_compare_digest = True
        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if not isinstance(op, (ast.Eq, ast.NotEq)):
                    continue
                for operand in (node.left, comparator):
                    text = ast.unparse(operand).lower()
                    if "principal" in text:
                        bare_hits.append(ast.unparse(node))
    return uses_compare_digest, bare_hits


def test_approval_ref_resolve_binds_the_principal_with_compare_digest() -> None:
    """`resolve()` delegates the comparison to `approvals.principal_matches` --
    checked below, on that function, for the same discipline this test held
    directly before the delegation existed -- rather than comparing inline."""
    source = inspect.getsource(approval_ref.resolve)
    tree = ast.parse(source)
    func_node = tree.body[0]
    _, bare_hits = _check(func_node)
    assert not bare_hits, f"a bare ==/!= compares a principal directly: {bare_hits}"
    assert "principal_matches" in source, (
        "resolve() must bind the principal through approvals.principal_matches"
    )


def test_principal_matches_itself_uses_compare_digest() -> None:
    source = inspect.getsource(approvals.principal_matches)
    tree = ast.parse(source)
    func_node = tree.body[0]
    uses_compare_digest, bare_hits = _check(func_node)
    assert uses_compare_digest, "principal_matches must compare with hmac.compare_digest"
    assert not bare_hits, f"a bare ==/!= compares a principal directly: {bare_hits}"


def test_report_route_binds_the_decide_principal_with_compare_digest() -> None:
    source = inspect.getsource(app_module.create_app)
    tree = ast.parse(source)
    func_node = _find_function(tree, "report")
    uses_compare_digest, bare_hits = _check(func_node)
    assert uses_compare_digest, (
        "the /v1/report handler must compare principals with hmac.compare_digest"
    )
    assert not bare_hits, f"a bare ==/!= compares a principal directly: {bare_hits}"
