# The decision reference

A decision reference is a small, plain JSON object naming one onedoor
decision. It exists so that a process which asks onedoor for a decision and
then carries out the action elsewhere — inside a separate observability or
run-tracking system, say — can record which decision it acted on, in a form
anyone holding an export of onedoor's own audit log can independently check.

Neither system needs to know about the other's internals. They share only
this shape:

```json
{
  "format": "onedoor-decision-ref/1",
  "request_id": "<the decide request's id>",
  "decision_digest": "sha256:<hex>",
  "verdict": "permit | deny | propose",
  "issuer": "<the onedoor deployment's declared id>"
}
```

## What onedoor returns

Every decide response — over HTTP (`POST /v1/decide`, `POST /v1/report`,
`POST /v1/approvals/{id}/approve`) and from the in-process engine
(`decide_and_reserve`, `evaluate_and_execute`, `resume_approval`) — carries a
`decision_ref` alongside its ordinary reply, **once a deployment has
configured an issuer id** (`EngineConfig.issuer`, or `ONEDOOR_ISSUER` for the
HTTP service). A deployment that has not configured one gets no reference at
all: onedoor never fabricates an issuer id from a hostname or any other
runtime detail.

- **`request_id`** is the id of the decide request that produced this
  decision — the join key between onedoor's own record and whatever else
  names the same action.
- **`verdict`** is one of `permit`, `deny`, or `propose` — a permitted action
  that runs in dry-run is still `permit` (the decision authorised it; the
  policy simply did not let it act for real), and a proposal awaiting human
  approval is `propose`.
- **`issuer`** is the deployment's own declared identity, configured once and
  used for every reference it issues.
- **`decision_digest`** is described below; it is the field that makes the
  reference checkable rather than merely a claim.

When an approval or a mandate ratification resumes a previously-proposed
action, the resumption runs as a fresh decide with its own new request id,
and the reference it returns names **that resumption's own decision** — not
the original proposal. The original proposal's own reference still exists,
naming its own row; the two are linked in onedoor's audit log the same way
any propose-then-resume pair already is, but the reference itself always
describes the decision it came from, not an earlier one.

A connector failure after a permitted action starts does not change the
reference: it still names the original `permit` decision, because that is
what was decided. What happened to the connector afterward is a separate
fact, reported separately.

### The verdict mapping

A reference may say `permit` only when onedoor actually enforced a permit.
This table maps every `Decision` value, and mode, to what a decide call
returns:

| `Decision` | Mode | Reference returned |
|---|---|---|
| `EXECUTED` | enforce (an ordinary auto or confirmed real execution) | `permit` |
| `EXECUTED` | observe (`effective_tier` is `Tier.OBSERVE`) | **none** |
| `DRY_RUN` | dry-run | **none** |
| `PROPOSED` | — | `propose` |
| `DENIED` | — | `deny` |
| `FAILED` | — (a report-time outcome, never a decide-time verdict) | **none** |

- **Dry-run:** nothing was executed, so there is nothing a reference could
  cite. Returning `permit` here (an earlier cut of this feature's own
  mistake) would let a run claim a decision that never actually ran.
- **Observe mode:** the action goes ahead whatever policy says — that is
  what "observe" means — so a `permit` reference would claim a decision
  that gated nothing. `EXECUTED` is the same `Decision` value an ordinary
  enforced permit gets; what tells them apart is the row's own
  `effective_tier`, not the `decision` column.
- If observe mode records the policy's would-be verdict, that stays in the
  audit row exactly as it does today — reading the export still shows what
  policy would have said. It simply never appears inside a reference, since
  a reference specifically claims "this was enforced."
- The practical effect: a run whose gated stage happened to be running
  under observe mode has no reference to cite, and shows "no decision
  cited" to whatever is checking — which is the truth. Telling that apart
  from "this action was never gated in the first place" is not this
  reference's job; see the limit below.

## How the digest is computed

`decision_digest` is the SHA-256 of the canonical JSON rendering of the exact
audit row the decision was recorded as — the same row, and the same
rendering, that `python -m onedoor.export` writes for that row. One function
computes this in both places, so a digest taken at the moment of decision and
one recomputed later from an export can never quietly drift apart into two
different ideas of what "the row" was.

The canonical rendering is: every column of the row, keys sorted, no
floating-point number ever appears (every numeric column on this table is
either an integer or an already-exact decimal string), compact separators. It
does not depend on whether onedoor's own hash-chaining is enabled for the
deployment — chaining's own columns are ordinary columns on the row like any
other, present and populated when chaining is on, present and empty when it
is off, hashed either way as whatever they actually hold.

It is also vocabulary-agnostic: `0.8.0`'s switch from `cap_value`/`cap_rate` to
`budget_exhausted`/`rate_exhausted` (and the accompanying `budget` object shape
change) does not change the digest of a row sealed before the switch — the
canonical rendering hashes whatever the row's columns actually hold, never a
re-encoding of them under the current vocabulary. A reference issued against a
pre-`0.8.0` row still checks `matches` today.

## How a holder of an export checks a reference

Given an export file (as `python -m onedoor.export` writes it) and a
reference, `python -m onedoor.decision_ref check --export <file> --ref <ref>`
answers exactly one of four things, each with its own exit code:

| Answer | Exit code | Meaning |
|---|---|---|
| `matches` | 0 | A row in the export has exactly this digest. |
| `digest mismatch` | 1 | A row shares the reference's `request_id`, but none has the claimed digest — the record has been altered, or the reference names something else. |
| `not in export` | 2 | No row in the export shares the `request_id` at all. |
| `malformed ref` | 3 | The reference itself is not a well-formed `onedoor-decision-ref/1` object. |

The checker is a small function using only the Python standard library
(`onedoor.decision_ref.check`, and the digest function it calls,
`onedoor.decision_digest.decision_digest`), so a system that only ever needs
to check references — never to run onedoor itself — can vendor those two
functions without taking on onedoor's own dependencies.

## How the executor and the MCP proxy expose it

The in-process engine (`onedoor.guardrail.executor.EngineConfig.issuer`) and
the HTTP service (`ONEDOOR_ISSUER`) both configure the same thing: whether,
and as whom, decide calls issue references. Anything calling
`decide_and_reserve`, `evaluate_and_execute` or `resume_approval` directly
gets the reference on the object those functions already return — no
separate hook is needed there.

The MCP proxy (`onedoor.mcp.proxy.Proxy`) is different: it sits between an
agent and a downstream tool server, speaking that pair's own MCP wire format
on both sides, and does not own the shape of what it forwards. It cannot
embed a reference inside a downstream tool's own JSON-RPC response without
conflating two different messages. Instead it keeps `Proxy.last_decision_ref`
— the reference to the most recent decision it acted on, `None` before any
call or when no issuer is configured — as a documented hook for whatever
wraps the proxy to read.

**This is safe without a lock because the proxy handles exactly one call at
a time.** `Proxy.serve` is a plain synchronous loop over one stdin stream:
deciding, forwarding to the downstream subprocess, reporting the outcome,
and writing the response all block the same thread, in order, before the
next line is even read. Nothing in the proxy imports threading or asyncio,
and MCP-over-stdio gives it exactly one input stream to read from, so there
is no second call for one to race against. A caller does need to read
`last_decision_ref` before starting its next call through the same proxy —
the same discipline it already needs for reading that call's own ordinary
MCP response before sending another.

## The limit

**A reference proves that a run cites an unaltered decision; it does not
prove that every action was gated.** A component that never asks onedoor at
all, or that asks and then ignores the answer, simply produces no reference
— and nothing here can tell that story apart from "this action was never
gated in the first place" from the reference alone. Telling those two apart
is the job of whatever declares, in its own terms, which actions were
*supposed* to carry a reference, and then shows where one is missing.
