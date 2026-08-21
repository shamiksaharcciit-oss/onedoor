# `0.3.6` — implementation tickets for the code agent

**Release:** `0.3.6` (hygiene; no AADP status change except the LiteLLM example
becoming conformant). **Baseline:** `0.3.5` @ `3dfe3cd` + `cbb8414` (CI).
**Nothing here is core-gated.** Core confirmed: proceed, ping on release.

**Standing Definition of Done** (all tickets): implementation + tests + full suite
green + `CONFORMANCE.md` row updated + docs touched where behaviour is user-visible.
**Review rule:** delivery reads every diff and runs the suite. Do not report a ticket
done on the strength of a summary.

---

## ND-021 — Make the LiteLLM guardrail conformant (report after the act)

**Size S–M · AADP two-phase contract · the cheapest credibility fix on the list**

### The defect
`examples/litellm_guardrail.py`, in `_decide`:

```python
if isinstance(outcome, PermittedIntent):
    # Example simplification: the gateway executes immediately after a
    # permitted pre-call, so report here. Production: report the real
    # outcome from async_post_call_success_hook.
    report_result(outcome, conn=self.conn, ok=True,
                  payload={"enforced_by": "litellm pre_call"}, error=None, now=now)
    return
```

It reports `ok=True` **before the gateway has done anything**. That is a violation of
the two-phase contract this project exists to define, shipped as a documented example
(`docs/integration-litellm.md`) of the standard's own reference implementation. Core
confirmed the draft cites it and currently describes it honestly as non-conformant;
that description becomes false the moment this lands, so **ping core on release**.

### The fix — option (a), confirmed by core
Split decide from report across the two hooks.

1. **`_decide` returns the `PermittedIntent`** instead of reporting. Denial, proposal
   and dry-run paths keep raising `OneDoorRejection` exactly as they do.
2. **`async_pre_call_hook`** stores the intent in a pending map keyed by LiteLLM's
   per-call identifier (`data["litellm_call_id"]`, with a documented fallback if
   absent) and returns.
3. **`async_post_call_success_hook`** pops the intent and calls
   `report_result(..., ok=True, payload={...})` with a payload describing the real
   result (model, token usage if available) rather than `{"enforced_by": ...}`.
4. **`async_post_call_failure_hook`** pops the intent and reports `ok=False` with the
   error string. **Do not skip this** — an unreported permit is the whole reason
   reservation reclamation exists, and an example that leaks permits teaches the wrong
   pattern.

### Constraints — read before writing
- **Correlation key.** If `litellm_call_id` is unavailable on either side, do not
  invent a global "last intent" variable — that is wrong under concurrency. Use the
  identifier LiteLLM actually threads through; if none exists, say so in the module
  docstring and key on the object identity of `data`.
- **The pending map is in-memory, and that is a known limitation, not an oversight.**
  Document it in the module docstring in the same register the codebase already uses:
  a gateway restart between pre-call and post-call strands the permit, and the
  reservation reclaimer (`0.3.4`) releases its budget on the deadline. This mirrors
  `ND-010` in the service and should not be silently patched over.
- **Do not over-invest in the `report_result` call sites.** `ND-039` replaces
  `ok: bool` with an outcome parameter in `0.4.0`; these call sites will be touched
  again. Write them plainly.

### Tests (`tests/examples/test_litellm_guardrail.py`, new)
1. **The conformance test:** after `async_pre_call_hook` on a permitted action, assert
   the audit contains an `exec_intent` row and **no `exec_result` row**. This is the
   test that would have caught the original defect; it is the point of the ticket.
2. After `async_post_call_success_hook`, assert exactly one `exec_result` row linked to
   that intent, `connector_ok = 1`.
3. Failure path: `async_post_call_failure_hook` yields `connector_ok = 0` and the error
   recorded.
4. Concurrency: two interleaved calls with distinct ids each report against their own
   intent — no cross-talk.
5. Denied / proposed / dry-run still raise `OneDoorRejection` and write **no**
   `exec_result`.

### Docs
`docs/integration-litellm.md`: remove the "example simplification" caveat, describe the
two-hook flow, and keep an explicit note that the pending map is in-process.

---

## ND-024 — Retire or document the vestigial schema

**Size S · no behaviour change · reader-honesty fix**

### The finding
`onedoor/store/migrations/0001_init.sql` still identifies itself as the **"Sutradhar M0
schema"** and creates four tables. Nothing under `onedoor/` reads three of them:

| Table | Status |
|---|---|
| `intake_policy` | no reader — vestigial |
| `preferences` | no reader — vestigial |
| `sessions` | no reader — vestigial |
| `push_subscriptions` | **keep** — genuinely planned (`ND-026`, web-push delivery) |

Dead schema in a governance product invites a reader to assume governed surfaces that
do not exist. That is the same class of problem as the LiteLLM example: a published
artifact implying something untrue.

### The fix
Migrations are **forward-only** — do not edit `0001_init.sql`'s `CREATE` statements.

1. Add migration **`0006_retire_vestigial.sql`** dropping `intake_policy`,
   `preferences`, `sessions`. Confirm with a fresh grep at implementation time that no
   reader has appeared; if one has, stop and report rather than dropping.
2. Rewrite `0001_init.sql`'s **header comment only** — "Sutradhar M0 schema" → an
   accurate description of the onedoor initial schema, with a line noting that some
   tables it creates are dropped in `0006` and why (history is preserved by the
   migration chain, not by editing the past).
3. Add a comment above `push_subscriptions` stating it is reserved for `ND-026` and
   intentionally unread today — so the next person does not delete it.

### Migration-number coordination
`0006` is the next free number and `ND-001`/`ND-002` will also want migrations. **This
ticket takes `0006`**; the `0.4.0` row-format work starts at `0007`. Record the
assignment in `BACKLOG.md` when this lands so two branches do not both claim a number.

### Tests
1. A fresh `Database.init()` produces a schema **without** the three dropped tables and
   **with** `push_subscriptions`.
2. An existing `0.3.5` database migrates forward cleanly, and the append-only triggers
   on `actions_audit` and `policy_versions` survive the migration.
3. The full suite passes unchanged — this must be a no-op for engine behaviour.

---

## ND-036 — Reconcile the repo's `ROADMAP.md`

**Size S**

The repository carries its own `ROADMAP.md`, distinct from the working roadmap this
backlog was built from. Two roadmap documents will diverge, and readers of the repo will
take the public one as current — it already predates every ruling in Responses 001–004.

Replace its body with a short pointer: what onedoor is, and that the live delivery
artifacts are `BACKLOG.md` (what is being built) and `CONFORMANCE.md` (what conforms to
AADP today). Keep it short enough that it cannot go stale again.

---

## README fixes (fold into `0.3.6`, no separate ticket)

1. **Line 83 says `pytest  # 111 tests`.** The baseline is 135 and rising. Core flagged
   it: it *under*claims, but stale is stale, and it now sits next to a live CI badge
   that shows the real number. Either state 135 or — better, since this will go stale
   again — drop the count and let the badge carry it.
2. Confirm the badge row added with `cbb8414` renders (CI, PyPI, Python versions,
   licence).

---

## Release checklist for `0.3.6`

1. All three tickets merged, suite green on both matrix jobs.
2. Version bump `0.3.5` → `0.3.6` in `pyproject.toml`; tag; changelog entry naming the
   LiteLLM conformance fix explicitly.
3. `CONFORMANCE.md`: LiteLLM row ❌ → ✅ packaged-conformant, with the new test as
   evidence; `ND-024` closes N3; `ND-036` closes N4.
4. **Ping core on release.** The §implstatus revision it triggers now carries three
   things, not one: the LiteLLM change, the obligation-machinery gap disclosure
   (`N6`/`ND-038`), and the `not_attempted` mishandling (`ND-039`, Escalation 005).
