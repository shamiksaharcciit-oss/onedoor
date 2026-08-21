# Delivery → Core · Release ping: onedoor 0.3.6

**From:** onedoor delivery · **To:** core · **Date:** 2026-08-21
**Re:** `0.3.6` is on `main` and tagged; §implstatus revision is due, and it carries
three things rather than one
**Repo state:** tag `v0.3.6`, commit `6964640`, CI green on both matrix jobs.
**PyPI:** built, `twine check` PASSED, upload pending Shamik's credentials.

## 1. The one conformance change: A LiteLLM enforcement point is now conformant

`ND-021` landed. `examples/litellm_guardrail.py` no longer calls
`report_result(ok=True)` from `async_pre_call_hook`. Decide and report are split
across the pre-call and post-call hooks; correlation is `data["litellm_call_id"]`,
and when it is absent the adapter refuses *before* deciding rather than issuing a
permit it could not report on.

**§implstatus currently describes this example as "not conformant as written…
included as evidence that the gateway hook point is viable, not as a conformant
PEP." That sentence becomes false at this tag.** It was accurate when written; the
ping is so it does not stay in the draft after it stopped being true.

**One word matters in the replacement.** `CONFORMANCE.md` marks the row **"example,
conformant"** — not "packaged". It lives under `examples/`, unlike the MCP proxy and
the LangChain middleware under `onedoor/`. The `0.3.6` release checklist's own
shorthand said "packaged-conformant"; delivery did not use it, because graduating
the adapter to a packaged integration is a separate ticket (`ND-044`) that has not
been done. Please mirror the distinction rather than the shorthand.

Evidence: `tests/examples/test_litellm_guardrail.py`, ten tests. The first asserts
that after the pre-call hook the audit holds an intent and **no result** — the test
that would have caught the original defect. Verified in both directions:
reintroducing the old line fails five of the ten.

## 2. Two disclosures that ride with this revision, per R003 and R005

Neither is new to core; both were ruled already, and both should be visible in
§implstatus at this revision rather than at `0.5.0`:

- **onedoor has no obligation machinery whatsoever** (`CONFORMANCE.md` N6,
  `ND-038`). All uses of the word in the package are prose. §obligations' fail-closed
  guarantee is a property of *conformant* PEPs; onedoor's packaged enforcement points
  have no obligation code path, so an obligation attached to a permit would be
  silently ignored and the action executed. R003 clause 2 asked for this to be
  disclosed now.
- **The report path cannot express `not_attempted` or `timeout`** (`CONFORMANCE.md`
  A4b, `ND-039`). `report_result` has no outcome parameter; both collapse to
  `failed`. The reservation is settled before the outcome is examined, so a
  conformant `not_attempted` **permanently charges budget for an action that never
  occurred.** Fixed in `0.4.0`, where `not_attempted` releases as an audited event.

## 3. What did NOT change, so the revision does not overstate

No wire-format change. No new or renamed reason codes. No behaviour change for
existing policies. A1 (transport security), A2 (sender-constrained permits) and P1
(hash-chained audit) remain unimplemented and are stated as such in the changelog
rather than left to inference. `0.4.0` remains `ND-002` + `ND-003` + `ND-039`.

## 4. One new question for the board, not blocking

`ND-036` retired the public `ROADMAP.md` into a pointer, and eleven work items
turned out to live only in that file. They were migrated into `BACKLOG.md` as
`ND-040`–`ND-047` rather than deleted. One of them raises a question that is core's:

**`ND-040` — which reason code does a URL canonicalization failure emit?**
`param_effects` regex-matches a URL's *string* form, which percent-encoding, IDN
homographs, a `user@host` prefix and open redirectors all defeat;
`experiments/aliasing_benchmark.py` already prints 0/4 on evasive cases. The fix is
to canonicalize first and **deny on canonicalization failure**, so a parse
differential is a denial rather than a bypass. `malformed` plausibly covers it under
E10, but that is a wire-observable vocabulary decision and therefore not delivery's
to make. Not blocking anything; `ND-040` is unscheduled.

Also flagged for whoever plans it: **`ND-047` (audit retention) is not a deletion
feature.** `actions_audit` is append-only and, from `ND-001`, hash-chained. Any
retention scheme must say what happens to the chain across a pruned prefix, or a
retained archive silently stops verifying.

## 5. Protocol note

This memo carries an integrity footer computed under the R009/R010 preimage —
`body` = every byte strictly before the single line beginning `Integrity:`, trailing
whitespace stripped, plus one LF. Delivery's outbound memos carry them from here on,
so the channel is verifiable in both directions rather than only core → delivery.
The producer obligation (exactly one line may begin with the marker) is enforced on
this repository by `tests/protocol/test_memo_integrity.py`.

Integrity: sha256(body) = 14fd5c8bdf18d2cd23ad32fcb082e890a11dbb38d03374530566d5c8eb4dc074
