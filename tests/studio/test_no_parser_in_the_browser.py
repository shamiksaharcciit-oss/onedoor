"""`ND-056` / T1 — live validation added a fetch, and this is the fence that keeps it dumb.

R063 §1 is the design being protected: the panes sync through the server *because the
server owns the only parser*, and **they cannot drift because there is nothing to drift
between**. Live validation is the first feature with an obvious temptation to break
that — parse in the browser and skip the round trip — and the temptation gets stronger
under time pressure, which is exactly when a fence has to be structural rather than
remembered.

A browser-side mirror of the policy parser would be a second implementation in a second
language, disagreeing first on precisely the inputs this engine exists to be careful
about: decimal strings, unicode, key order, `null` against absent. V7 proved that is not
hypothetical — the two panes disagreed on `'500.00'` vs `'500'` within an hour of the
claim that they could not.
"""

from __future__ import annotations

import re

from onedoor.studio import shell

POLICY_VOCABULARY = (
    "action_type",
    "compensating_command",
    "cost_param",
    "strict_params",
    "eur_day",
    "eur_month",
    "param_effects",
    "dry_run",
    "min_tier",
    "bounds",
    "tier",
    "caps",
    "effects",
    "policies",
)
"""Field names from `Policy`, `Bounds` and `Caps`. If any of these appears in a script,
the browser has started to know what a policy is."""

PARSING_VOCABULARY = (
    "JSON.parse",
    "yaml",
    "YAML",
    "split(':')",
    'split(":")',
    "parseFloat",
    "parseInt",
    "Number(",
    "RegExp",
)
"""Ways a script would begin to read the text rather than post it."""


def test_no_declared_script_knows_what_a_policy_is() -> None:
    for script in shell.DECLARED_SCRIPTS:
        for word in POLICY_VOCABULARY:
            assert word not in script, (
                f"{word!r} appears in a served script. The browser has started to know "
                "what a policy is, which is the second parser arriving one field at a time."
            )


def test_no_declared_script_parses_anything() -> None:
    for script in shell.DECLARED_SCRIPTS:
        for word in PARSING_VOCABULARY:
            assert word not in script, f"{word!r} appears in a served script"


def test_the_live_script_only_moves_text_and_html() -> None:
    """What it is allowed to do, stated positively.

    It reads a textarea's value, posts it, and assigns the response to `innerHTML`. Every
    judgement in that HTML was made on the server by the engine's own loader.
    """
    script = shell.LIVE_VALIDATE_SCRIPT
    assert "box.value" in script, "it reads the text"
    assert "encodeURIComponent(box.value)" in script, "and posts it without inspecting it"
    assert "out.innerHTML=html" in script, "and renders what the server sent back"
    # The response is used whole. Nothing slices, filters or interprets it.
    assert "html.replace" not in script and "html.split" not in script


SINK = re.compile(r"(innerHTML|innerText|textContent)\s*=\s*([A-Za-z_$][\w$]*|['\"])")
"""Every assignment into the page, and what is on the right of it."""


def test_the_browser_displays_only_what_the_server_sent() -> None:
    """The requirement, after two proxies for it turned out to be wrong.

    The first version of this test banned verdict words anywhere in the script and failed
    on `box.dataset.validate` — `valid` inside the name of a ROUTE. The second scanned
    string literals and failed on `'validation'` — the id of a DIV. Two false positives of
    the same class is the signal that the proxy is not the requirement (R058 §5), so the
    proxy is gone and the requirement is stated directly:

    **nothing but a value fetched from the server may be written into the page.** A
    script that cannot put its own text on screen cannot render a verdict, whatever
    words it happens to contain — and that is checkable, where "does this script have an
    opinion" is not.
    """
    for script in shell.DECLARED_SCRIPTS:
        for _, right in SINK.findall(script):
            assert right not in ("'", '"'), (
                "a script writes a string LITERAL into the page. Everything the reader "
                "sees must have come from the server, which is the only thing that "
                "parsed anything."
            )


def test_the_live_scripts_only_page_write_is_the_servers_response() -> None:
    sinks = SINK.findall(shell.LIVE_VALIDATE_SCRIPT)
    assert sinks == [("innerHTML", "html")], (
        f"expected exactly one write, of the fetched response; found {sinks}"
    )


def test_the_sink_fence_can_fail() -> None:
    """Sabotage, both directions: a literal write must be caught, the real one must pass."""
    liar = "(function(){out.innerHTML='invalid policy'})();"
    caught = [right for _, right in SINK.findall(liar) if right in ("'", '"')]
    assert caught, "the fence would have walked past a browser-authored verdict"

    honest = [right for _, right in SINK.findall(shell.LIVE_VALIDATE_SCRIPT) if right in ("'", '"')]
    assert not honest, "and it must not condemn the real script"


def test_the_fence_can_fail() -> None:
    """Sabotage: a checker that has never been shown a lie has never been shown to look.

    Both fences are run against a script that really does parse, and both must catch it.
    """
    liar = (
        "(function(){var p=JSON.parse(box.value);"
        "if(!p.action_type||!p.compensating_command){show('invalid')}})();"
    )

    caught_vocab = [w for w in POLICY_VOCABULARY if w in liar]
    assert caught_vocab, "the policy-vocabulary fence would have walked past a real parser"

    caught_parse = [w for w in PARSING_VOCABULARY if w in liar]
    assert caught_parse, "the parsing fence would have walked past a real parser"


def test_the_page_runs_no_inline_handlers() -> None:
    """An `onclick=` is a script the allow-list never sees."""
    from onedoor.studio import screens
    from onedoor.studio import shell as shell_module

    html = shell_module.render(
        body=screens.upload_missing_body(),
        banner=shell_module.Banner(in_force=None, ratified=None, policies=0, effects=0),
        active="drafts",
    )
    assert not re.findall(r"\son[a-z]+\s*=\s*[\"']", html)
