# Changelog

onedoor is the reference implementation of the AADP Internet-Draft
(`draft-saha-aadp`). Per-requirement conformance status, gaps included, lives in
[CONFORMANCE.md](CONFORMANCE.md); the ticket-by-ticket plan is in
[BACKLOG.md](BACKLOG.md).

## 0.3.6 — 2026-08-21

Hygiene and one real conformance fix. No wire-format change; no behaviour change
for existing policies.

### The reference implementation stops publishing a contract violation (ND-021)

`examples/litellm_guardrail.py` called `report_result(ok=True)` from
`async_pre_call_hook` — **asserting an action had succeeded before the gateway had
done anything.** That is a violation of the two-phase contract this project exists
to define, shipped as a documented example and cited in the draft's Implementation
Status as "not conformant as written".

Decide and report are now split across hooks: the pre-call hook decides and holds
the permit, reporting nothing; `async_post_call_success_hook` and
`async_post_call_failure_hook` report the real outcome. Correlation is
`data["litellm_call_id"]`; when it is absent the adapter refuses *before* deciding,
so no permit is issued that it could not report on. The pending-intent map is in
process memory — a documented limitation, mirroring `ND-010` in the decision
service, with reservation reclamation as the backstop.

Ten new tests, including the regression that fails against the old behaviour.

### Also in this release

- **`ND-024`** — the vestigial `intake_policy`, `preferences` and `sessions` tables
  (inherited from a pre-onedoor product) are dropped by migration `0006`.
  `push_subscriptions` is kept and now says in a comment that it is reserved for
  web-push delivery, so nobody mistakes it for dead schema.
- **`ND-025`** — CI actually enforces the gates. `ruff`, `ruff format`, `mypy
  --strict` and `pytest` run on a 3.12/3.13 matrix; `ruff` is **pinned**, because an
  unpinned linter makes CI non-deterministic. All four now pass; none of them did
  before.
- **`ND-036`** — `ROADMAP.md` is a pointer to the live documents rather than a
  stale feature list. Eleven work items that lived only in it were migrated into
  `BACKLOG.md` rather than deleted.
- **Packaging:** a `[litellm]` extra. The LiteLLM example imported a package no
  extra installed, so anyone following the docs hit `ModuleNotFoundError`.
- **Repository integrity:** `.gitattributes` forces LF and freezes the vendored,
  digest-pinned reference artifact byte-for-byte. Windows' `core.autocrlf` default
  silently rewrote those bytes, which made every pinned manifest fail verification
  in a way that reads as *evidence tampering* rather than as an encoding bug.
- **`README`** no longer advertises a stale test count; the CI badge carries it.

### Fixed

- `pytest` and `python -m pytest` no longer disagree. 19 test modules import
  `tests.conftest`, which needs the repository root on `sys.path`; `python -m`
  supplies it implicitly and the bare `pytest` that CI runs does not. The suite
  passed locally and could not even be collected in CI.

### Known gaps, stated rather than implied

- No obligation machinery at all (`CONFORMANCE.md` N6 / `ND-038`). A conformant
  PDP obligation attached to a permit would be silently ignored by onedoor's own
  enforcement points.
- `report_result` has no outcome parameter, so `not_attempted` and `timeout`
  collapse into `failed` (`CONFORMANCE.md` A4b / `ND-039`). A reservation is
  settled before the outcome is examined, which charges budget for an action that
  may never have occurred. Fixed in `0.4.0`.
- Transport security (A1), sender-constrained permits (A2) and hash-chained audit
  entries (P1) are not implemented.

## Earlier releases

Reconstructed from git tags; these predate this file.

| Version | Tag subject |
|---|---|
| 0.3.5 | integrations: onedoor as LangChain agent middleware |
| 0.3.4 | guardrail: reservation reclamation (AADP §6) |
| 0.3.3 | F7 — every euro cap was inert unless the caller set `cost_eur` by hand |
| 0.3.2 | onedoor did not work on Windows |
| 0.3.1 | release the packaging fix |
