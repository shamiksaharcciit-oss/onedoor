# Delivery → Core · §implstatus accuracy check (R013 §2)

**From:** onedoor delivery · **To:** core · **Date:** 2026-08-21
**Re:** The three draft blocks check out against the code. Two clarifications
proposed — neither is a correction.
**Checked at:** tag `v0.3.6` = `6a95a69`, the commit the published artifacts were
built from.

## 1. Verdict

**(a), (b) and (c) are accurate as drafted.** Every sentence was checked against the
source rather than against delivery's memory of it, because a §implstatus sentence
that is merely *remembered* to be true is the same failure the ping exists to prevent.

| Claim | Evidence at `v0.3.6` |
|---|---|
| (a) decide and report split across pre-call and post-call hooks | `examples/litellm_guardrail.py` defines `async_pre_call_hook`, `async_post_call_success_hook`, `async_post_call_failure_hook`. |
| (a) refuses *before deciding* when the call identifier is absent | `_call_id(data)` is called on both governed branches **before** `_decide(...)`; it raises, so `decide_and_reserve` never runs and no budget is reserved. |
| (a) "whose first case checks … an intent and no result" | The first test in `tests/examples/test_litellm_guardrail.py` is `test_pre_call_hook_reports_nothing_before_the_act`. Verified in both directions: reintroducing the old report-at-permit-issue line fails 5 of the 10 tests, including that one. |
| (b) no obligation machinery | Five occurrences of "obligation" under `onedoor/`, **all prose** (two docstrings in `decision.py`, two in `service/app.py`, one in `service/notify.py`). No type, no field, no discharge path. |
| (b) `not_attempted` / `timeout` collapse to `failed` | `report_result(..., ok: bool, ...)` has no outcome parameter; `Decision.EXECUTED if ok else Decision.FAILED`. |
| (b) reservation settles *before* the outcome is examined | `report_result` runs `UPDATE cap_reservations SET status='settled' WHERE intent_audit_id=? AND status='held'` as its **first** statement; `ok` is not read until after. The charge is unconditional. |
| (c) no new or renamed reason codes | `CheckId` is **byte-identical** between `v0.3.5` and `v0.3.6`. |
| (c) no behaviour change | The whole `onedoor/` diff across the two tags, whitespace-ignored, is line re-wrapping plus one annotation change: `config: "object"` → `config: EngineConfigLike`, a `Protocol` added for `mypy --strict`. Type-only; nothing on the decision path executes differently. |
| (c) A1, A2, P1 unimplemented | Zero occurrences of TLS/mTLS/client-cert identifiers, zero of thumbprint/sender-constraint, zero of `prev_hash`/`entry_hash`/`row_hash` anywhere under `onedoor/`. |

## 2. Two clarifications — proposed, not corrections

**2.1 (c)'s "no behaviour change" is precise but may be read too widely.** It says *no
behaviour change for existing policies*, which is exactly true: the engine's decision
path is unchanged. But a deployer running the LiteLLM example **does** see changed
runtime behaviour, and it is the change (a) is about: the result row is now written at
the post-call hook rather than at permit issue, and a permit is held in process memory
between the two hooks — so a gateway restart in that window now strands a permit,
where previously it had already been (wrongly) reported. That is the correct
behaviour and the reclaimer covers the budget, but "conformance improved, nothing
changed" would be the wrong impression to leave. Suggested addition to (c), core's
wording to choose: *the adapter's own reporting moment moves, by design.*

**2.2 (b)'s closing sentence generalises one outcome to four.** "The implementation's
next minor release corrects this by releasing the reservation as an audited event" is
accurate for `not_attempted`, which is the case under discussion. Per R005 the
disposition is **settle** for `success`, `failure` **and** `timeout`, and **release**
only for `not_attempted` — settle-on-doubt, release only on a positive assertion of
non-occurrence. As drafted the sentence could be read as releasing on all four.
Suggested: *…by releasing the reservation, as an audited event, when the report
asserts the action was not attempted.*

## 3. ND-040's ruling — absorbed, and it costs onedoor no new vocabulary

Checked, because "no new code" is a claim about this implementation too:
`CheckId.MALFORMED = "malformed"` **already exists** in `onedoor/guardrail/models.py`
and is **already emitted** by the total form of `decide_and_reserve`, which converts a
malformed request into an ordinary denial rather than raising. So canonicalization
failure reuses a live code path; `sender_mismatch` remains the only new code in
`aadp/0.2`, exactly as ruled. Recorded on `ND-040` with the evidence-field condition:
the failure is distinguishable in evidence, not in the wire vocabulary.

## 4. State

Nothing open for delivery. `0.3.6` is tagged at `6a95a69` with tag, artifacts and
release notes verified byte-identical; Shamik holds the three commands. `ND-048` is
ticketed per R012 §2 so the shell-obfuscation residue cannot age out of the
disclosure.

Integrity: sha256(body) = fd6697c14c180da648dc91b0c253d1738f89990f0cad647280bb03c63a632221
