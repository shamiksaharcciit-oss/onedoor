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

## The limit

**A reference proves that a run cites an unaltered decision; it does not
prove that every action was gated.** A component that never asks onedoor at
all, or that asks and then ignores the answer, simply produces no reference
— and nothing here can tell that story apart from "this action was never
gated in the first place" from the reference alone. Telling those two apart
is the job of whatever declares, in its own terms, which actions were
*supposed* to carry a reference, and then shows where one is missing.
