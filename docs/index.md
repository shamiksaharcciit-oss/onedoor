# onedoor documentation

**onedoor** is a tiered guardrail engine for agentic systems. Every action —
scheduled, rule-fired, LLM-proposed, or human-clicked — is a structured
`ActionRequest` evaluated by one decision pipeline before anything touches the
world. The model proposes; the policy layer disposes.

## Pick your integration

| You have | Use | Guide |
|---|---|---|
| A Python codebase (agent, framework, backend) | Embed the library | [Library integration](integration-library.md) |
| Anything that speaks HTTP (gateways, services in any language) | The decision service | [Decision service](integration-service.md) |
| An MCP host + tool servers (Claude Desktop, any agent host) | The MCP proxy | [MCP proxy](integration-mcp.md) |
| A LiteLLM proxy | The custom guardrail adapter | [LiteLLM adapter](integration-litellm.md) |
| A LangGraph / LangChain agent | Governed tool wrapper + interrupts | [LangGraph](integration-langgraph.md) |

Then write your policies: [Policy reference](policy-reference.md).

## The three-minute mental model

1. **One door.** Callers never execute; they submit an `ActionRequest`
   (action type + params + rationale) to the engine.
2. **Ordered checks.** Kill switch → policy lookup (unknown action types are
   denied) → tier-1 integrity (no undo → no autonomy) → bounds →
   dry-run → caps (reserved race-free) → intent recorded.
3. **Four outcomes.** *Permitted* (an obligation: you enforce, then report),
   *denied* (with a typed reason), *proposed* (waiting for a human approval),
   *dry-run* (logged, nothing happens).
4. **Everything audited.** Append-only log: decisions, results, denials,
   approvals, kill-switch blocks — every row carries a reason code.

## Autonomy tiers

| Tier | Meaning |
|---|---|
| 0 | Observe only (reads; exempt from the kill switch) |
| 1 | Auto-execute — reversible, in-bounds, with an undo window |
| 2 | Auto-execute under caps (rate + €/day + €/month) |
| 3 | Propose-and-confirm — approvals with TTL |

## Design guarantees you can rely on

- An action type absent from the policy table **cannot** execute: it is
  denied with reason `default_deny`, and never proposed.
- A Tier-1 policy without a `compensating_command` **cannot** load (boot
  failure) and cannot execute (runtime demotion to Tier 3).
- Bounds are validated before a proposal is created, so approvers only ever
  see in-bounds requests.
- A dry-run never consumes caps.
- Two concurrent requests cannot share the last slot under a cap
  (check-and-reserve inside the deciding transaction).
- The audit log is append-only; results link to intents; undo links to its
  parent.

## Building a release

`python tools/build_release.py`, run from a git checkout (it reads `HEAD`
itself, via `git rev-parse`/`git archive`; a bare export has nothing for
that to read), is the one recipe: it refuses to run unless the active Python
holds exactly the tool versions `requirements-build.txt` pins (create that
venv with `pip install -r requirements-build.txt --require-hashes`), builds
from a clean `git archive HEAD` with `SOURCE_DATE_EPOCH` set to HEAD's own
committer time, and closes the sdist's one remaining non-determinism (see
`tools/reproducible_sdist.py`). It prints four lines of its own -- the tool
versions, the epoch and commit, both sha256 values -- beside `build`'s own,
uncaptured output. A plain `python -m build` installs whatever setuptools
PyPI is currently serving instead of this repository's pin — the gap that
once let a release ship a wheel built with the wrong version. Release tags are
annotated from now on, tagged by the no-reply address
(`noreply@anthropic.com`); a published tag is never moved.
