# Recording onedoor decisions in a onetrace run

A onetrace step that takes an action can record *which* onedoor decision allowed it,
and the record proves it: anyone holding the decision export can check, with no
network call, that the decision exists unaltered and that it permitted this step —
and, where a bound permit was used, that the permit covered exactly the action the
step sent.

**This page shows the onedoor side only.** The onetrace side — declaring a step
gated, `ctx.decision(...)`, the `authorization` receipt block, onetrace-verify's new
rows — arrives in onetrace 0.5; `tests/vectors/` is published now so that work can
vendor against stable values ahead of it. See
[`onetrace_onedoor_integration_design.md`](../onetrace_onedoor_integration_design.md)
for the whole shape across both projects.

## One gated step, end to end

### 1. Decide

```python
from onedoor.guardrail.decision import decide_and_reserve

outcome = decide_and_reserve(request, conn=conn, config=config, now=now)
```

`config.issuer` must be set for `outcome.decision_ref` to be populated — absent
otherwise, never a guessed value. If the action type declares `present_bound` and
`bound_permit_action_type`, and the request carries a presenter key thumbprint,
`outcome.bound_permit` is also set.

### 2. Receive the reference and the permit

Every integration surface hands both back, in a documented field or attribute, not
by changing the shape of what a caller already read:

| Surface | Reference | Permit |
|---|---|---|
| Library (`decide_and_reserve` / `report_result`) | `.decision_ref` | `.bound_permit` |
| HTTP decision service (`POST /v1/decide`, `/v1/report`) | `decision_ref` | `bound_permit` |
| LangChain middleware (`OneDoorMiddleware`) | `.last_decision_ref` | `.last_bound_permit` |
| MCP proxy (`Proxy`) | `.last_decision_ref` | `.last_bound_permit` |

The reference is always the same small object regardless of surface:

```json
{
  "format": "onedoor-decision-ref/1",
  "request_id": "...",
  "decision_digest": "sha256:...",
  "verdict": "permit",
  "issuer": "https://onedoor.example/deployment"
}
```

A replayed answer to the same `request_id` (a retried decide call, say) carries the
same reference and the same id field the live answer did — never a different name
for the same row depending on which call happened to answer it. The permit is
never reissued on a replay: it is a short-lived, one-time credential, not evidence,
and is not stored anywhere to reissue from.

### 3. Act, then record

Inside the gated step, after onedoor answers and before the action:

```python
ctx.decision(outcome.decision_ref, permit=outcome.bound_permit, action=action_object)
```

(This is the onetrace-side call `ctx.decision(...)` the design note describes —
shown here for the shape of what this surface hands it, not as onedoor API.)
`action_object` is the same JSON object the step is about to send, recorded by its
digest (`onedoor.permit.action.action_digest`, domain tag + JCS) — the one thing
that lets a permit be checked against what the step actually did, not merely what
it was decided to do.

### 4. What a holder of the export can check, later, with no network call

```
python -m onedoor.decision_ref check --export <export.jsonl> --ref <ref.json>
```

Five outcomes, each its own exit code: `matches`, `digest_mismatch`,
`not_in_export`, `malformed_ref`, `export_damaged`. Checking a permit against a
recorded action is narrower — a signature check against an issuer's published key,
the action digest compared to the signed claim, and the `exp` claim against a given
time — not the full recipient replay/audience binding `onedoor.permit.recipient`
does for a live presentation.

## What this does not claim

- A citation shows that a run names an existing, unaltered decision. It does not
  show that every action in the run was gated, only that every step declared gated
  cited one.
- A permit check shows the decision covered the action object a step *recorded*. It
  does not show that whatever received the action got exactly that object — that
  is the recipient's own check, at presentation time, not this.
- Nothing here says a decision was *right*, only that it was made and is unaltered.

## See also

- [`tests/vectors/README.md`](../tests/vectors/README.md) — the published vectors
  a vendoring consumer tests against, with their exact format.
- `onedoor.decision_ref`, `onedoor.decision_digest` — stdlib-only, vendorable
  without onedoor's own dependency tree.
