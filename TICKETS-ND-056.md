# `ND-056` — Studio authoring paths · decomposition and build record

**Ruled:** `Core_Forward_006_Studio_Authoring_Paths_2026-08-30` (`f20677b3…`) and
`Core_to_Delivery_Response_066_2026-08-30` (`16781a0c…`).
**Proposal:** `escalations/PROPOSAL-20260830-ND-056.md` (`1a5de44a…`), which reported six
contradictions before any code and which R066 accepted as the F046-shape answer.
**Constraints:** additive only · the freeze on breaking changes holds · `ND-053`/`ND-054`
stay frozen · oneview compliance · tests-first.
**Shipping:** as **`0.7.0`**, gated on Shamik's dogfooding pass. T3's slip target is
**`0.7.1`**, alone.

---

## The three tracks

| | Track | State | Where |
|---|---|---|---|
| **T1** | Editor + upload + staged validation | **built** | `staging.py`, `forecast.py`, upload and fragment routes |
| **T2** | Policy REST API, no approval-by-API | **built** | `api.py`, `/api/v1/*` |
| **T3** | Natural-language authoring, six walls | **built** | `live_proposer.py`, `/propose` |

## The six contradictions, and how each was resolved

| | Contradiction | Resolution |
|---|---|---|
| **C1** | The "no approval-by-API" wall was already breached by a **shipped** route (`POST /draft/{id}/ratify`, in `0.6.2` on PyPI, undocumented and untested by path) | R066 §1: keep it this release, add a **witness test** and a **deprecation field in its own response**, document it truthfully, retire it with the actor-identity work. Core registered the gap as its own: the wall was written by the author of a tree that already served one |
| **C2** | `0.6.3` cut from `main` would ship the entire ND-055 arc — `main` is 13 commits and 11,241 insertions past `v0.6.2` | R066 §2: release the V1–V8 hold, **renumber to `0.7.0`** because a version number describes content, and **gate the tag on the dogfooding pass** |
| **C3** | "The FULL loader rulebook" is unreachable without changing fail-closed boot semantics or building the forbidden second validator | R066 §3: delivery's wording replaces core's — *every refusal the loader can produce for this candidate, at the stage that produces it* — and `INCOMPLETE_NOTICE` still renders beside every list |
| **C4** | Two of the five named checks are **not loader refusals**: a euro cap without `cost_param` loads and denies at decision time (`cost_unknown`); `strict_params` is a property of requests | R066 §3: two separately-typed lists, never merged, and every forecast **names the reason code** the engine will record |
| **C5** | The five walls omitted constitution principle 4, the dark-surface list | R066 §4: core's defect — the constitution always bound T3. Built as **wall 6** |
| **C6** | "F046 shape" names an artifact this channel does not hold | R066 §4: cited in error, will not be sent; the inferred shape is confirmed. *A directive cites only artifacts the receiving channel holds, or carries the shape inline* |

## Rulings answered

| | Question | Ruling |
|---|---|---|
| **Q9** | The F046 shape | Confirmed; F046 is another channel's artifact |
| **Q10** | `python-multipart` into `[studio]` | Approved, as a **recorded reversal**: a file field is not the text field the original decision was about, and hand-parsing multipart is a second parser |
| **Q11** | T3's quality gate | The constitution's §2 bar — **benchmarked with published misses**, not "reviewed" |
| **Q12** | `openapi_url` only | Approved at `/api/v1/openapi.json`; `/docs` and `/redoc` stay off |
| **Q13** | Q8's green-run count | **Interrupted at ten**; the count restarts |
| **Q14** | Wall 6 | Binding |

## Defects self-caught during the build

Counted because the register is worth more with them than without.

| Where | What |
|---|---|
| T1 | `staging` ordered the stages `load → schema → effects → rules`; `load_file` validates **before** building effects, so a file bad in two ways would have been reported against a stage the engine never reaches. **Found by writing the AST fence's premise, before the fence had run once** |
| T1 | The no-browser-parser fence banned verdict words anywhere in a script and failed on `box.dataset.validate` — `valid` inside a **route name** |
| T1 | Rewritten to scan string literals, the same fence failed on `'validation'` — the id of a **div**. Two false positives of one class ⇒ the proxy is not the requirement (R058 §5); replaced with *nothing but a value fetched from the server may be written into the page* |
| T2 | The blunt no-external-origin check failed on the published OpenAPI schema, which embeds a docstring naming `http://127.0.0.1:8787`. Third instance; replaced with *every host named must be loopback*, plus a separate fetchable-reference check |
| T3 | The auto-repair and no-fallback fences failed on this module's own **docstrings** — `fixup` and `FixtureProposer` inside the prose explaining that neither exists. **V7's checker-reads-prose defect, fourth exhibit.** Fixed by walking the AST and stripping docstrings |
| T3 | The auto-repair fence was scoped to the whole module and condemned `strip` in the mention **tokeniser**, which touches the operator's description and never the model's output |
| T3 | A **false gap**: a description saying "refunds" against a declared `payments.refund` reported it uncovered. A dark-surface list that cries wolf is worse than one that misses. Fixed with a declared singular fold — *never a score, always a declared transform* |
| Session | `INTEGRITY.md` regenerated through `Path.write_text`, whose newline translation rewrote all 200 lines as **CRLF** — the corruption that file documents as relay failure mode 2, introduced by the tool that maintains it. Caught by reading a diff claiming 201 insertions for a one-row change |
| Session | The dogfooding test's own docstring said "two" commands could not run when there were four, and named `NOT_EXECUTED`, a constant already renamed |

## Defects found in core's artifacts

Registered on the shelf R058 §4 opened, and **core registered the first two against itself
before delivery had to argue them.**

| Artifact | Defect | Ruling |
|---|---|---|
| Forward 006 §2 | The "no approval-by-API" wall, written by the author of a tree that already served one | R066 §1 — and the missing law: *every route declares what it is permitted to do* |
| Forward 006 §2 | "The FULL loader rulebook" — an absolute the engine does not offer | R066 §3, delivery's wording adopted |
| Forward 006 §2 | Two of five named checks are runtime behaviour, not loader refusals | R066 §3 |
| Forward 006 §2 | Principle 4 omitted from the walls though the constitution binds T3 | R066 §4 |
| Forward 006 §3.1 | "F046 shape" — an artifact of a different channel | R066 §4 |
| Forward 006 §3.2 | `0.6.3` as the release number, on an assumption C2 dissolved | R066 §2 |

## The law this arc added

**Every route declares what it is permitted to do** — routes are classed (read /
draft-mutating / binding), and a binding route must name its actor and its ceremony. The
V8 universal pass enumerated the route table and applied six laws; none asked what a route
may *do*, which is why a ratifying route survived it. `tests/studio/test_api.py` and the
JSON-surface pass in `tests/studio/test_law_tests.py` hold it now.

## What has not been done

- **Nothing has shipped.** The last release is `0.6.2`.
- **No breaking change landed.** Every track is additive; `ND-053`/`ND-054` untouched.
- **T3 has never run against a real endpoint.** Every T3 test replaces the socket and
  nothing else. Q11's bar — a live benchmark with published misses — **is not met**, and
  it needs Shamik's endpoint, key and spend approval. If it is not met by Sept 5, T3
  slips to `0.7.1` by its designed path.
- **The Studio still has not been run by a person** since `0.6.2`. Shamik's pass, and it
  **gates the tag** (R066 §2) rather than following it.

## Closed by `Core_to_Delivery_Response_067_2026-08-30`

The build is **accepted as reported**, subject only to the two human gates that were
never this channel's to clear. All three defect fixes ratified; the second sharpened into
law (see `CONFORMANCE.md` §5).

**The user manual is ruled core-owned** (R067 §2). Delivery was right that a PDF is not a
source it can edit honestly, and the resolution is **ownership, not a workaround**: the
manual is core's artifact, built from source on core's side, and core owes the `0.7.0`
edition — new sections for the three tracks, cover line unchanged and now simply true —
after the dogfooding pass and before the Sept 7 tag, so that what it documents is what an
operator has actually seen. `docs/OneDoor_User_Manual.pdf` is an **incoming binary, never
a build input**, and Forward 006 §4's "manual updated to match" is discharged on core's
ledger. It is off this ticket's list of owed work.

**What the channel now holds:** three tracks feature-complete on 2026-08-30, five days of
margin to the Sept 5 bar, two human gates (the dogfooding pass by Sept 5; T3's funding by
Sept 3), one core deliverable (the manual), and a release on Sept 7 by Shamik's hands
under the number R066 §2 gave it.

**The channel holds.** Nothing in the build queue outranks the launch queue this week.
