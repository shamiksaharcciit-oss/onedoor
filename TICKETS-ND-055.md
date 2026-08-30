# `ND-055` — Policy Studio v2, "The Ledger Room" · decomposition

**Ruled:** `Core_to_Delivery_Response_055_2026-08-28` (BUILD AUTHORIZED), with
`Core_to_Delivery_Response_056_2026-08-28` on sequencing and the seal boundary, and
`Forward_005` on V8(a)'s test shape.
**Binding design authority:** `Design_Note_Policy_Studio_V2_2026-08-28.md`
(digest `118c61b3…`) and the approved mockup, artifact
`ee38c587-7761-4773-881a-764d21c0abdc`. Deviations are escalations, not judgment calls.
**Constraints:** additive only · never gates launch · `ND-053`/`ND-054` stay frozen.
**Shipping:** P0 shipped as `0.6.2`. **V1–V8 ship as `0.7.0`, after Sept 12, never before.**

---

# `ND-055` — the full-arc ledger

**Every stage, every law test, every owed item: discharged or named.** R063 §6 asks for
this before `0.7.0` assembles after Sept 12.

**Status: CLOSED by `Core_to_Delivery_Response_065_2026-08-28`** — recorded as the finest sustained arc of the programme. P0 shipped in `0.6.2`; V1–V8 are built and held for the `0.7.0`
line. Nothing in V1–V8 has shipped, and nothing breaking landed during the freeze.

## The eight stages

| | Stage | State | Ruled by |
|---|---|---|---|
| **P0** | F-G empty state, F-H database trap | **shipped `0.6.2`**, verified by core against PyPI | R055, R058 §0 |
| **V1** | Shell: tokens, tabs, header, version banner | built | R055, R056, R057 |
| **V2** | S1 Policies | built | R055, R058 |
| **V3** | S4 History | built | R055, R059 |
| **V4** | S5 Live state | built | R055, R060 |
| **V5** | S3 Drafts + the ceremony | built | R055, R061 |
| **V6** | Re-evaluate under version — the flagship | built | R055, R062 |
| **V7** | S2 Editor | built | R055, R063 |
| **V8** | S6 Verify + the universal law pass | built | R055, R063 |

## The six law tests R055 V8 owed

| | Law | Where it is enforced | State |
|---|---|---|---|
| **(a)** | seal never signals state, positive form | `assertions.seal_state_violations`, over every emitted page | **discharged** |
| **(b)** | an empty state for every list view | parametrised over all five list screens, against a fresh store | **discharged** |
| **(c)** | no external origin on any page | every served page, plus the script allow-list | **discharged** — and it caught `/docs` and `/redoc` |
| **(d)** | honesty footnote verbatim | wherever the validator renders, checked escaped **and** unescaped | **discharged** |
| **(e)** | digest format 8…4, copy handle, full on hover | every `digest` span on every page | **discharged** |
| **(f)** | a control that cannot act must not render enabled | every form checked against the app's route table; no button outside a form | **discharged** |

## Owed items folded in by R055

| Item | State |
|---|---|
| **R015's owed positive-form seal test** | **discharged** — landed V1, universal in V8 |
| **oneview §5.4, anchor-status out of the seal** | **discharged** — the spec contradicts its own §4; §4 wins, the spec is not edited, and a test proves the clause never reached a page |
| **R056 §4's S4/S6 seal migration** | **discharged** in V1, seven violations caught then cleared, both required tests inverted in the same commit |
| **Forward 005's sabotage pair** | **discharged** in V1 |
| **R057 §5's contrast correction + CI numbers** | **discharged** in V1/V3; the matrices print in the run summary since V7 |
| **R058 §4's `--faint` audit** | **discharged** in V3, by use, with the one available exemption declined |
| **R058 §6's Q5 two-voice layout** | **discharged** in V5 |
| **R059 §3's `key_id` shape** | **specced, frozen** — post-Sept-12, see Q7 |

## Defects self-caught across the arc

Counted because the register is worth more with them than without.

| Where | What |
|---|---|
| V1 | `banner_for` read `ratifications` from the draft store; every shell route raised on a fresh install |
| V1 | the strengthened seal check condemned `.store-warning` — it read a comment as a selector |
| V3 | a filter value absent from the ledger vanished from the form while still filtering the page |
| V3 (Q6 fix) | the first 404 fix answered `application/json` wrapping HTML — the lie moved headers |
| V5 | `Divergence.receipt` `None` while the state says the replay ran — a fourth case mypy found |
| V7 | the two panes disagreed on `500.00` vs `500`, within an hour of the claim that they cannot |
| V7 | the editor's own fence check failed on the docstring documenting the fence |
| V8 | `/docs`, `/redoc`, `/openapi.json` broke the header's promise, live since V1 |
| V8 | `/` and `/draft/{id}` still served the pre-V1 design |
| V8 | F-H's warning and F-G's `curl` line stranded by V5's move to `/drafts` |
| V8 | three served tests had silently stopped testing |

## Defects found in core's own artifacts

Registered on core's instruction, on the shelf R058 §4 opened.

| Artifact | Defect | Ruling |
|---|---|---|
| The approved mockup | state chips fail WCAG AA at chip size; refusal worst at 3.33:1 | R057 §5 — *accessibility is not a deviation from the design; inaccessibility is* |
| `R055` §V2 | described a **deny tier the engine does not have** | R058 §4 |
| `R055` §V2 | cited `descriptions.py` as a plain-language renderer; it is not one | R058 (Q5) |
| `R055` §V3 | assumed the ledger records a caller identity; it does not | R059 §3 |
| `R060` §5 | the word **"irreversibility"** — false, and falsely frightening | R061 §2 — *finality is not irreversibility* |
| oneview spec §5.4 | *"anchor status in seal color"*, contradicting its own §4 | R055 V8(a); closed in V8 |

## Open, and named rather than closed

- **Q7 — the ledger records no caller identity.** Ruled (R059 §3): a non-secret `key_id`
  assigned at creation, `actor_id` on `actions_audit`, backfill nothing, `audit.append`
  grows the parameter in the same change. **Schema change; frozen until Sept 12.**
- **Q8 — one pytest-internal `StashKey` failure**, seen once, never reproduced. The
  reporting move was made on design grounds and **explicitly not as a fix** (R062 §4). The
  entry closes only by recurrence-with-investigation, or by a healthy number of
  consecutive passes recorded as *"not observed since the reporting move; cause never
  established."* **R064 §4 set the bar: twenty consecutive green full-suite runs,
  counted from the reporting move.** A recurrence before twenty reopens it as a real
  investigation with the full stash trace captured.

  **Banked: ten, then INTERRUPTED, then six.** The ten were three local gate runs across
  V7/V8, two CI jobs on `eb5df1a`, one direct `pytest -q`, two local gate runs in that
  stage, one CI job on `d785d4a`, and one on the closing commit.

  **The streak broke on 2026-08-30**, on a fresh full-suite run during the `ND-056` build:
  `2 failed, 1168 passed, 9 skipped`. **The `StashKey` failure did NOT recur** — one
  failure was the digest register refusing an unarchived memo (the register working), the
  other a latent environment defect in `tests/mcp/test_proxy_demo.py` fixed in `4725663`.
  Delivery recorded the streak as interrupted before asking, which is the reading that
  cost something; **Q13 ruled it interrupted at ten** (R066 §7).

  R067 §3 rules **when** counting resumes — at the first green full-suite run *after* the
  interrupting run, not when the ruling arrived, because a green run is a fact about the
  tree and Q13 was declaratory rather than constitutive. That reasoning is adopted.

  **R067 §3 states the bank reads six. Read off the runs, delivery counts five, and only
  four of them consecutive.** Raised in
  `escalations/ACCURACY-CHECK-Q8-count-2026-08-30.md` rather than adopted: *a number
  transcribed from a memo instead of read from the runs is R010 broken in miniature*, and
  this channel has already corrected one of its own commit messages for exactly that
  (`54ea440`).

  | Run | Result |
  |---|---|
  | `ad8de62` gate | **green** — 1171 passed, 9 skipped |
  | *(mid-T1)* | **RED** — four gates red, then two red suites while the register refused an unarchived memo |
  | `733d852` gate | **green** — 1238 |
  | `caa24c2` gate | **green** — 1275 |
  | `1b8f7c4` gate | **green** — 1308 |
  | `22b5dfd` gate | **green** — 1314 |

  Five green; the red runs between the first and second break consecutiveness, so on
  R064 §4's wording — *twenty **consecutive** green full-suite runs* — the streak stands
  at **four**. Whether a deliberately-red mid-build run breaks a streak meant to measure
  *flakiness* is a real question and core's to answer; it is not delivery's to settle in
  the direction that flatters the ledger. **Recorded as four pending that answer**, which
  is the costly reading again.
- **`ND-053`, `ND-054`** — frozen, unchanged, and `ND-054`'s divergence is noted at the
  editor's decimal fields in the words the engine's behaviour justifies today.

## What has not been done

- **Nothing in V1–V8 has shipped.** The last release is `0.6.2`.
- **No breaking change landed during the freeze.** Every stage is additive.
- **The Studio has not been run by an operator since `0.6.2`.** Every claim above rests on
  tests and on served requests in this repository, not on a person using it — which is
  how F-A, F-G and F-H were found, and is worth arranging again before `0.7.0`.


---

## The dogfooding walkthrough (R064 §5)

`docs/DOGFOODING.md`, with `tests/studio/test_dogfooding.py` reading **that file** and
running what it finds. The commands are extracted from the document rather than copied
into the test: a test running *similar* commands would drift the moment either changed,
and the drift would be invisible — test green, walkthrough wrong, and the person following
it finds out. X-11's reasoning, applied to a runbook.

Seven commands. **Three are run** to completion with their exit codes asserted; **four are
checked** with the reason and with whatever the command claims verified instead. Each is
marked in the document, so a reader sees the distinction rather than only the test.

| Command | | What happens |
|---|---|---|
| `python -m venv .venv` | `[checked]` | would test venv, not onedoor |
| `pip install -e ".[studio]"` | `[checked]` | needs network; the extra is declared and everything it names imports |
| `python -m onedoor.studio --help` | **`[run]`** | exit 0, and all four documented flags present |
| `python -m onedoor.studio --db … --port 8787` | `[checked]` | serves forever; its argv goes through the real parser, an unknown flag is refused |
| `curl -X POST …/drafts` | `[checked]` | CI need not have curl; the route is checked against the app's POST table and the field against the form |
| `python -m onedoor.studio.walkthrough --db onedoor.db` | **`[run]`** | exit 0, and exactly one audit row written |
| `python -m onedoor.studio.verify receipt.json snapshot.json` | **`[run]`** | **all three exit codes**, against a receipt the test itself ratified |

The last one is R064 §5's requirement met literally: the walkthrough ends with a verify
command run **against a receipt the walkthrough itself produced**, not a fixture.

`onedoor/studio/walkthrough.py` is new and is a **walkthrough aid, not a product feature**
— it exists so step 7 has a decision to look at without a person writing Python. It writes
to the enforcer store, which the Studio never does; it is a separate command precisely so
that distinction stays visible.

### Defect self-caught: the walkthrough overclaimed its own testing

The first draft said *"every command below is executed… two cannot be"*. **Three could
not**: the start command serves forever, and the curl line needs a binary CI need not
have. Both were being validated, not run, and the document called them executed.

That is the overclaim this project spends its time removing from other people's pages, and
it does not get to keep one of its own. The claim now names two categories, marks every
command with which it is, and `test_every_command_is_accounted_for_as_run_or_as_checked`
requires the two lists to **partition the document exactly** — nothing missing, nothing
invented, nothing in both. Sabotage-verified: a command added to the document fails the
build by name.

---

## Stage board

| | Stage | State |
|---|---|---|
| **P0** | F-G empty state, F-H database trap | **shipped** — `0.6.2` |
| **V1** | Shell: tokens, tabs, header, version banner | **built** |
| **V2** | S1 Policies | **built** |
| **V3** | S4 History · Q4 · Q6 | **built** |
| **V4** | S5 Live state | **built** |
| **V5** | S3 Drafts · the ceremony · Q5 | **built** |
| **V6** | Re-evaluate under version — the flagship | **built** |
| **V7** | S2 Editor · Q8's move | **built** |
| **V8** | S6 Verify + the law tests | **built** |

---

## V1 — the shell

### What was built

`onedoor/studio/tokens.py`, `onedoor/studio/_vendor/LEDGER_ROOM_TOKENS.css`,
`onedoor/studio/shell.py`, four routes in `server.py`, `banner_for()`.

**The palette is the Studio's own, and the divergence is specified rather than drift.**
oneview's ground is `#0b0d10`; the design note says *"warm charcoal/umber (#1c1713
family), never blue-black"*, and the mockup carries `#1c1713`. The note also settles
the reach of the shared spec: *"§3 static fence does not apply, but §4 (seal never
state) binds everywhere."* **The rule travels and the palette does not** — hence two
token modules and one law. The block is vendored, digest-pinned (`7a3a19a3…`), fenced
`-text`, excluded from ruff, and declared in `package-data`; `tokens.py` raises rather
than falling back, because a Studio that silently renders in last week's palette is a
Studio that ships in last week's palette.

The palette also carries a state colour oneview has no name for — `--review`. oneview
renders verdicts that have happened; the Studio renders policy, where *requires
approval* is a first-class outcome.

### Three things the shell deliberately does not do

**No design-study banner.** The mockup carries *"design study · … · not the shipped
product"*. The note asks for it *"on every mockup frame until built"* — this is the
built thing, and carrying it in would be the page lying about itself in the one line
whose job is to say what the page is.

**Tabs are links, not buttons.** The mockup switches tabs in JavaScript because it is
one static file. R055 V1 asks for the F-A regression against *"every new route"* —
routes, server-side — and the Studio has held a no-JavaScript line since F-G. Same
design, delivered by the transport this app has.

**No `cursor:copy` on digests — ~~and this one was wrong~~, amended by R057 §2.**
V1 argued that copy-on-click needs JavaScript, that the app runs none, and that a cursor
promising a copy it cannot perform is an overclaim rendered in CSS. The second and third
clauses hold. **The first premise did not:** R055 §3 permits *"minimal inline JS"* in the
same breath as it mandates copy-on-click, so V1 dropped a required affordance to keep a
rule core had never made — and did it by reasoning from the Studio's habit rather than
from the ruling's words. *The summary-vs-source law, met from a new direction: the habit
was real, and it was not the authority.*

The affordance is now progressive enhancement, and the V8(f) point survives intact
because it moved into the mechanism: `COPY_SCRIPT` adds `copyable` in the same loop body
that attaches the handler, and returns early where no clipboard exists. Nothing the
server emits carries the class. *An affordance is a promise; the promise and the thing
must be one act.*

An unbuilt tab is not a link either, for the same reason — it renders as text naming
the stage that builds it. `shell.TABS` is the only place that knowledge lives, so the
tab bar and the routes cannot disagree, and the served-route tests read their
parametrisation from it.

### The third outcome the banner would otherwise have hidden

The version in force and the ratification date are two facts from one store, and they
can disagree — a store edited by another Studio, a restore from backup, policy applied
by hand. So the banner has three words, not two: a date, `never ratified` (the log is
empty), and **`not ratified through this Studio`** (the log is not empty and does not
contain the version in force). A banner that printed the latest ratification's date
beside a version that ratification did not produce would be wrong in the most expensive
direction: *confidently, and in the field an auditor reads first.*

### Defect self-caught: the wrong store

`banner_for` first called `ratify.latest(state.studio)`. `ratifications` is an
**enforcer** table — migration `0017`, because a ratification receipt is a fact about
the store whose rules it changed — so every shell route raised `no such table:
ratifications` on a fresh install.

It was caught by `test_every_shell_route_renders_over_http`, **through the server, on
the first request**, and by none of the library-level tests. F-A's lesson holding
exactly: *a served surface is tested through the server.* The rule it broke also has a
name: **select on fields you have verified, not the record** — `state.studio` and
`state.enforcer` are both `Connection`, and only one has the table.

### The seal migration (R056 §4) — in this commit, with the tests

R056 **superseded R049 §3's `--seal` clause**: the rule binds everywhere, no
grandfathered screens. R049 §3 otherwise stands minus its fourth mechanism — *size,
position and weight remain, and three are enough.*

`assert_seal_never_signals_state` was strengthened to the **positive form** R055 V8(a)
asks for: rather than checking that `.verdict` rules avoid gold, it enumerates every
rule that *uses* a brand token and asks what routes it. The state vocabulary is read
from `studio.coverage`'s own enumerations, so a new state is inside the check the
moment it exists.

**Caught, then cleared — by name.**

*S4, `onedoor/viewer/coverage.py` — four, the four R056 names:*

1. `.row.declared_inert` — `border-left:3px solid var(--seal)`
2. `.row.declared_inert .state` — `color:var(--seal)`
3. `.row.uncovered_observed` — `border-left:3px solid var(--seal)`
4. `.tally .declared_inert b` — `color:var(--seal)`

*S6, `onedoor/viewer/proposal.py` — three:*

5. `section.asserted` — `border-left:3px solid var(--seal)`
6. `.row.declared_inert` — `border-left:3px solid var(--seal)`
7. `.uncovered` — `color:var(--seal)`

All seven now carry `--ink`, the page's own foreground: it makes the border **present**
without making it **mean**. `uncovered_observed` distinguishes by *texture* (dashed
against solid), which survives both the colour rule and a monochrome print.

`test_coverage_map.py:82` and `test_proposal.py:156` inverted **in this commit** — they
required `var(--seal)` on a state row, which became a test demanding a violation the
moment the law strengthened. *A test that requires a violation must not survive one
commit longer than the violation it protects.*

**Shown failing first.** With the CSS reverted to its pre-migration state and the tests
left as they now are, exactly four tests fail and only those:

```
FAILED test_seal_sabotage.py::test_no_skin_routes_the_brand_accent_by_state[S4 coverage]
FAILED test_seal_sabotage.py::test_no_skin_routes_the_brand_accent_by_state[S6 proposal]
FAILED test_coverage_map.py::test_the_map_still_distinguishes_its_states_visually
FAILED test_proposal.py::test_the_asserted_section_is_visibly_a_different_kind
4 failed, 38 passed
```

### Defect self-caught: the check condemned the innocent

The first run of the strengthened check reported `.store-warning` — F-H's empty-store
advice — as a violation. **It is not one**, and R056 §2 names it as the exact thing
that must not fire.

It fired because the rule parser read the explanatory comment above the rule as part of
the selector, so the rule inherited every word from the prose documenting it. **A check
that reads prose as selectors will condemn the code that documents itself best** — and
a check that condemns the innocent teaches people to route around it, which is worse
than the violation it caught. Comments are now stripped first;
`test_an_advisory_panel_in_gold_does_not_fire` holds the boundary from that side.

### The sabotage pair (Forward 005)

Two sabotages, not one. **Literal injection** proves the check reads the declaration;
**semantic-class route** proves it reads the selector — because nobody types `--seal`
into a rule called `.verdict`; they write a rule for a state and reach for the colour
that looks right. Both spellings of the accent are covered (`--seal` and the Studio's
`--gold`): a check that knew one name would pass the Studio by default, which is the
grandfather clause R056 removed.

---

## V2 — S1 Policies

`onedoor/studio/library.py` (read model), `onedoor/studio/screens.py` (markup), two
routes.

**It reads the snapshot behind the pinned version, not the live tables.** Through
`policy_loader.upsert` the two never disagree — it records a snapshot on every write —
but a row written around it makes them disagree, and then they are *different facts*:
the tables are what the next snapshot would hold, the pinned version is what the engine
is deciding against and what the header's digest names. A page built from the tables
would contradict the digest in its own header, on the screen an auditor uses to say what
was deployed. Tested by writing straight into the table and asserting the page does not
move — with a third assertion that the fixture actually created the disagreement, so the
test cannot pass by proving nothing.

**Three outcomes, and the middle one is the dangerous one.** No version in force; a
version whose snapshot cannot be read; a real set. Collapsing the second into the first
would tell an operator that **nothing is permitted** while the engine is permitting
things — the one error this page must never make. It renders as *"this is not an empty
policy set — the engine is deciding against rules this page cannot read."*

**The chip is a claim about what the engine will decide**, and `dry_run` outranks the
tier: a rule that would permit but runs dry permits nothing, and `allowed` would be the
screen making a promise the engine is not keeping.

**A correction to R055's own model of the engine.** V2 was written against tiers
`AUTO/CONFIRM/APPROVE/DENY`; the engine's are `OBSERVE/AUTO/AUTO_CAPPED/CONFIRM` and
**there is no deny tier at all** — refusal comes from default-deny, bounds, caps or the
kill switch. Each phrase was checked against `guardrail/decision.py` rather than inferred
from the constant's spelling; `OBSERVE` in particular returns `Decision.EXECUTED` and
*performs nothing*, returning at step 5 before bounds are evaluated. Three chips over
four tiers means one must be approximate, so `OBSERVE` wears `allowed` and the tier gets
its own column: **the approximation belongs where a second column already carries the
exact answer.**

**R015 caught on the way out.** `NumericBound(max=…)` dumps `{"max": "500", "min": null}`,
and rendering that would show an operator a bound they never wrote on the page that
exists to tell them what their rules say. Stripped recursively — the first nested shape
that needed it was two levels down.

### `descriptions.py` is not a plain-language renderer — R055 V2's pointer is wrong

R055 V2 says *"plain-language rendering (descriptions.py exists for this)"*.
`studio/descriptions.py` freezes **the operator's own words** as received data, the input
to S6's proposer, and contains no renderer. The design note asks for something else:
*"plain-language rendering of each rule beside its YAML"*, generated from the rule.

So `library.sentences()` was written — strictly derived, every clause from a field, and a
field with nothing to say produces no sentence rather than a reassuring one. **A rendering
that adds a clause the policy does not contain is a rendering that will be trusted for a
guarantee nobody wrote.**

Reported rather than silently resolved because the two are easy to conflate on screen —
what a rule **does** versus what someone **said it was for** — and conflating them is
exactly the mistake S6's asserted/measured split exists to prevent. **Q5 below.**

### The YAML pane shows JSON, deliberately

A hand-rolled YAML writer would be a second serializer for a format the loader already
parses one way, and the first quoting difference between them would be a screen showing
something the engine would not load. JSON is a subset of YAML, so what is shown is
loadable as written — the property that matters more than the file extension. Named for
what it is rather than labelled "YAML".

## V8 — S6 Verify, the universal law pass, and the owed items

`onedoor/studio/verify.py` (read model **and** the command), two routes,
`tests/studio/test_law_tests.py`.

### The deposition page, written for a stranger

R063 §6: assume the reader distrusts the operator, the vendor, and the page. So the page
does two honest things instead of one dishonest one — it **shows a verification that was
run**, and it **shows how to repeat it** without this program's cooperation:

> This page cannot verify anything for you. It was produced by the same software that
> produced the receipt, so it shows you a check that was run and the exact command to run
> it yourself, on files you hold, without this program's cooperation.

Ordered for that reader: **what to run, then the files, then what this software got** —
so the method is read before the answer, and the answer is never the first thing offered.

`python -m onedoor.studio.verify receipt.json snapshot.json` is real and new. It reads two
files, opens no database, and carries **three outcomes in the exit code as well as the
words**: `0` verified, `1` failed, `2` unreadable. *Unreadable is not a failed check* —
telling a stranger their receipt is bad when what is bad is their download would be the
worst error this page could make. The page and the command run the same
`ratify.verify_files` over the same bytes; a page that reimplemented the check would be a
second implementation of the answer, and R062 §1 has ruled on those.

### The universal pass caught two live pages no law had ever seen

The six laws passed on first run — and that would have been the wrong thing to report,
because **the first version of this file trusted my own list of paths**. Sabotaging each
law confirmed all six can fail; then reading the route table off the running app found
what the list was missing.

**Caught, then cleared — by name:**

1. **`/docs`** — FastAPI's Swagger UI, served from `cdn.jsdelivr.net`, with a favicon from
   `fastapi.tiangolo.com`.
2. **`/redoc`** — ReDoc from `cdn.jsdelivr.net`, fonts from `fonts.googleapis.com`.
3. **`/openapi.json`** — an API surface the Studio never meant to publish.
4. **`/`** — still rendering the **pre-V1 oneview canvas**. V5 moved Drafts to `/drafts`
   and left the old page live: the Studio served **two designs at once**, and the legacy
   one bypassed every law V8 makes universal.
5. **`/draft/{draft_id}`** — the same, one level down.

The first three are the sharper finding. **The Studio's own header promises "loopback
only — nothing leaves this machine", and two live pages made that false from V1 until
now.** Every per-screen test missed them for the same reason: *they only ever looked at
screens this project wrote.*

Auto-docs are off — the Studio is an operator GUI on loopback, not an API surface, and
its JSON endpoints are documented in the README where they cost no network call. `/` and
`/draft/{id}` **redirect** rather than 404, because `README` and `0.6.2`'s handover both
tell operators to open `http://127.0.0.1:8787`, and *a link that has been published is a
link that keeps working.*

`test_the_universe_of_this_file_is_the_app_itself` now derives its universe from the
app's route table, with two named exclusions. **A universal test whose universe is
incomplete is a per-screen test with ambition.**

### Two shipped fixes had been stranded by V5

Both surfaced while fixing the above, and both are `0.6.2` behaviour that quietly stopped
reaching operators when Drafts moved to `/drafts`:

6. **F-H's empty-store warning** — still rendered, on a page nothing linked to.
7. **F-G's `curl` one-liner** — same.

Restored on `/drafts`, with the warning given its own style (border and surface, never a
verdict colour, never the brand accent). Caught by the P0 regressions, which is what they
are for: *a shipped fix quietly stranded by a redesign* is invisible to every test that
only reads the new page.

### Three tests had silently stopped testing

8. With every tab built, `_unbuilt_paths()` returned empty and three parametrised served
   tests collected nothing — pytest reported `got empty parameter set for (path)`, and
   they sat in the suite guarding nothing.

Replaced with a fixture that registers a synthetic unbuilt tab, so the route factory, the
honest body and the F-A rerun stay under test for whoever adds the next screen — plus
`test_every_real_tab_is_built`, which fails if a tab is ever added unbuilt and says to
restore the parametrised form. **A guard has to survive the day it has nothing real to
guard.** `nav_html` gained a `tabs=` seam for the same reason.

### The owed oneview §5.4 item

**The vendored spec contradicts itself.** §4: seal gold never signals state. §5.4:
*"anchor status in seal color."* Anchor status **is** a state — anchored, not anchored,
unverifiable — so §4 wins and §5.4's clause does not survive it.

The spec is core's received data and digest-pinned, so **it is not edited**; the
resolution is recorded and enforced as a test, the same shape as the palette's corrections
layer. Nothing shipped ever implemented the clause, so the item closes by **proving the
defect never reached a page** rather than by removing it.

The positive-form seal test (R055 V8(a)) landed in V1 and is now asserted over every
emitted page rather than per-skin.


## V7 — S2 the editor, and Q8's approved move

`onedoor/studio/editor.py`, two routes, and the palette report relocated.

### "Always in sync" without a second parser

The obvious way to sync two panes is JavaScript: parse the raw pane in the browser and
mirror it both ways. **That is a second implementation of the policy parser**, in another
language, and the two would disagree on exactly the inputs this engine cares about most —
decimal strings, unicode, key order, `null` against absent. R062 §1 named the law for the
replay and it applies here unchanged.

So the panes sync **through the server**, which owns the only parser. Editing either pane
and submitting re-renders **both from one parsed model**. They cannot drift because there
is nothing to drift between: what each pane shows is one object, rendered twice. The cost
is a round trip; the benefit is that the raw pane always shows something the engine would
load, and the form never shows a value the raw pane would parse differently.

### Defect self-caught: the panes disagreed on the first try

`test_both_panes_are_rendered_from_one_object` failed on `'500.00' != '500'`. The guided
pane read model **attributes** (`Decimal("500.00")` → `"500.00"`) while the raw pane used
`model_dump()` (E8 canonical → `"500"`). **The two panes disagreeing is the one thing this
design claims is impossible**, and it was true within an hour of the claim.

Fixed by rendering the form from the dumped values too: one object, **one
canonicalisation**, rendered twice. The test that caught it is the test that exists for it.

### Two more of my own checks read prose as code

R058 §4's law arrived a second and third time in one sitting. The fence check scanned the
module source for `policy_loader` and **failed on the docstring sentence saying
`policy_loader.upsert` is never called** — condemning the module for documenting the very
fence it keeps. It now walks the **parsed AST**: imports and call names, never text. The
ticket-quote check failed because `TICKETS-ND-054.md` wraps the sentence across a line and
bolds it; it now normalises whitespace and strips emphasis, neither of which changes what
the ticket says.

### The ND-054 note

At all three decimal fields, and it describes **what the engine does today**:

> Decimal strings are accepted here and are what the draft stores. Be aware of how the
> engine treats them today: a cap reads a decimal string exactly, and a numeric bound over
> the same parameter refuses it. Declaring a numeric bound on a parameter therefore changes
> which wire types that action accepts.

R062 §5's constraint is tested as a forbidden-word list — no `will be`, `soon`, `until`,
`ND-054`, `planned`, `fixed`, `upcoming` — because *a note that describes tomorrow's
behaviour is aspiration dressed as capability, one field at a time.* A second test checks
the wording still matches what `TICKETS-ND-054.md` §3 measured on shipped code: a note that
drifted from the measurement would be a note about nothing.

**Not a character of the fix was implemented.** Decimals are parsed with `Decimal(text)`,
never through `float`, which is E8 and also the ND-054 hazard met from the other side.

### The form is a declared subset

`NOT_IN_THE_FORM` names the three fields the guided pane does not offer, and the page
prints them. Saving from the form uses `model_copy` over the existing rule rather than
rebuilding from the form alone — **a partial editor that writes a whole object deletes what
it never displayed.**

### Fence post one, asserted twice

Structurally: the module imports nothing that can write live rules and calls nothing named
like it, checked over the AST. Behaviourally: a served test edits a draft's cap to `9999`
and asserts the enforcer store's version pointer and `caps_json` are byte-identical
afterwards. A parse failure answers **400**, says the draft is unchanged, and writes
nothing.

## Q8 — the move, made on the approved grounds

The palette matrices moved from `capsys.disabled()` inside four tests to
`pytest_terminal_summary` in `tests/conftest.py`, with `tests/studio/palette_report.py`
holding the rendering. **Recorded as a design change, not a fix**, per R062 §4.

The split is the improvement: the tests keep every assertion that can fail a build and
lost every line that only announced. *A test that both measures and announces hides which
half failed.*

**The numbers are still in CI.** The workflow runs `pytest -q` directly, and the report
prints in that output — verified. The gate runner's console shows only the last three
lines of each gate, which is why the summary is absent there and present in CI.

**The flake stays open**, with R062 §4's two closing paths and no third.


## V6 — the flagship: re-evaluate under version

`onedoor/studio/reevaluate.py`, a block on the History detail page, and one query
parameter.

### The premise, verified as a test rather than as a sentence

R055 V6 asked that retrievability be checked first. It holds:
`policy_loader.record_snapshot` writes the whole set into `policy_versions` keyed by its
hash, `snapshot_for` returns it, `ratify._policies_at` rebuilds the `Policy` objects.
V4 already leaned on the same path for its budget limits. **No escalation was needed**,
and `test_policy_sets_are_retrievable_by_version` keeps the verification where it can
fail rather than in a report where it cannot.

### The engine decides, not this module

The replay builds a **scratch database in a temporary directory**, loads the historical
policies, and calls `decide_and_reserve` — the entry point the live service calls.
`backtest.run` established the pattern and the reason: *the instrument is identical, not
merely the answer plausible.* A hand-written comparison of rules would be a second
implementation of the verdict, and the two would disagree the first time anything subtle
changed. Asserted structurally: the module must contain `decide_and_reserve` and must
not contain a tier check, a counter read, or a `_verdict` function of its own.

**The control case is the strongest evidence the instrument is right:** replayed against
the version that actually decided, the engine reaches the verdict the record holds.

### Three outcomes, and the most dangerous available answer

| | rendered as |
|---|---|
| the replay ran | both verdicts, side by side, with `changed` true or false |
| the version has no snapshot | **`not retrievable`** — no verdict at all |
| the row cannot be rebuilt into a request | **`cannot be replayed`** — a different failure |

The middle row is the one that matters. An empty policy set replays as default-deny and
returns a confident `denied` — **the shape of a real verdict carrying none of its
meaning**, and the most dangerous answer this screen could give. `Comparison.changed`
returns `None` there, never `False`, so a comparison that could not be made can never
render as one that found no difference. The two failures never share a word: one is a
fact about the yardstick, the other about the question, and they have different
remedies.

The dropdown offers only what `snapshot_for` can serve (R056), read from
`policy_versions` rather than from the audit log's distinct version values — *a version
some row once named is not necessarily one this store can rebuild*, tested by inserting
a row naming a ghost version and asserting it never appears as an option.

### What the screen says (R061 §5)

**Both versions in the same breath** — *"Decided under `26e92ec9…520c`; replayed under
`0f4dca01…f248`"* — with the deciding version marked in the dropdown so a reader can
find the control case without comparing digests by eye. And the would-have sentence on
every state of the block, including the failures:

> This replays one recorded decision against a different version's rules. It says what
> would have been decided, not what will be. Nothing was re-executed and nothing in the
> ledger changed.

Both clauses are load-bearing. *Would have, not will* keeps the counterfactual from
reading as a prediction. **Nothing was re-executed** keeps it from reading as an action —
this page runs a decision function, and an operator who thinks a payment was attempted
twice has been badly misled by a button. Proven by eight served requests leaving the
ledger, the counters and the version pointer exactly where they were.

### A recurring mistake earns a named tool

`assert_reader_sees` in `tests/viewer/assertions.py`, written after the same error three
times: a constant containing an apostrophe reaches the page as `&#x27;`, and a test
asserting the raw constant fails against a page that is **correct**. It checks the
escaped form in the markup and the unescaped rendering back to the constant, which is
R061 §3's law with somewhere to live.


## V5 — S3 Drafts, the ceremony, and Q5's two voices

`onedoor/studio/drafts.py` (read model), five routes, and the two-voice pane on S1's
detail view. The Drafts tab moves from `/` to `/drafts` and the whole pipeline now wears
the ledger-room shell.

### The ceremony's gravity comes from what is true

R060 §5 shaped every sentence on the ratify page. It says three things — what will be in
force, what changes, what this does not undo — and a confirm. What it **refuses** to say
is the tested part:

- **Not "this cannot be undone."** That would be false *and* falsely frightening. The
  truth is narrower and more useful: there is no un-ratify, and **the way back is
  forward** — ratifying again, which is a new version and a new receipt, with the record
  keeping both. `test_the_ceremony_does_not_claim_the_change_cannot_be_undone` fails on
  the words "cannot be undone" and "irreversible".
- **No drama the engine does not do.** No countdown, no "are you sure", no "permanent" —
  asserted as a list of forbidden words.
- **The session note is described as what it is:** what this store knows, not an
  authenticated identity. The same discipline as `ratified_by_session`'s own naming.

The ceremony is a **GET before it is a POST**, and a served test proves reading it
ratifies nothing. Splitting the reading from the doing is the whole reason it is a page
and not a button.

### The backtest panel is about the past, and says so

*A backtest replays decisions this ledger already recorded. It says what would have
happened, not what will.* A divergence count read as a forecast is the overclaim this
screen most invites, so the limit is printed on the panel that could invite it.

**Each flip direction gets its own sentence**, one per direction, because a single "N
verdicts changed" hides the one an operator must never miss: **`permits what was
refused`**. Widening directions are marked apart from tightening ones — a count alone
treats a loosening and a tightening as the same event. A direction with no sentence is
rendered raw rather than paraphrased.

### The honesty footnote, verbatim and proven verbatim

`validate.INCOMPLETE_NOTICE` is interpolated from the constant, never retyped. The test
checks **both** the escaped markup and the unescaped rendering, because the page
correctly emits `engine&#x27;s` — asserting only the raw form would have made a
correctly-escaped page look like a paraphrase.

### A fourth case mypy found

`Divergence.receipt` is `BacktestReceipt | None` even when `state == ran`. That is a
fourth outcome — the replay reports it ran and carries no receipt — and it now has its
own words: *"this is a malformed result, not a clean one."* A panel rendering zeroes
there would report a clean replay that never happened. **Unverifiable and malformed are
failures to surface, never skips**, and a type checker is a perfectly good way to find
one.

### Q5 — the two voices, never merged

`library.frozen_words` reaches the operator's own words with **no new stored pointer**: a
ratification's `candidate_digest` *is* the proposal's `policy_digest`, so
`descriptions.records_for_policy` finds the derivation, and its `Mention` rows link
description phrases to action types.

Rendered as a **quotation, attributed, in a separate block** — never merged into the
derived sentences. The panel says in words that nothing above is derived from it and
nothing in it is checked against the rule, *so a reader can see where they differ*. R058
§6: the screen's value is exactly the gap between them, and merging would manufacture
agreement.

Three states, kept apart: a description that mentions the rule (quoted), a description
that **does not** mention it (said, because silence about a rule is itself a finding),
and no description at all (**the pane is omitted** — an empty quotation would read as an
operator who wrote nothing, which is a different fact from a rule never proposed through
the Studio).

### A refusal answers 409

R059 §2 applied: a refused ratification is not a server error and not a success — the
request was well-formed and the engine declined it. The body keeps the ceremony's own
words, with the named reason, and says *nothing was applied*. A missing session note
answers 400.


## V4 — S5 the live room

`onedoor/studio/live.py` (read model), one route.

### The kill switch: read-only, and here is the check R055 V4 asked for

**An admin API exists — and it is not one the Studio may use.** `POST /v1/killswitch`
lives on `onedoor.service`, the PDP. Both routes from the Studio to the switch break
something load-bearing:

1. **`killswitch.set_engaged(state.enforcer, …)` directly** — R047 §2 is that *the
   enforcer's database contains no row the Studio can edit*, with the ratification
   ceremony as the single sealed exception. A second write path makes that sentence
   false, and it is the sentence the two-process design rests on.
2. **Calling the service over HTTP** — that needs the PDP's admin credential inside a
   policy editor, which is exactly what R047 §1 separates the processes to prevent, and
   it would make a page promising *nothing leaves this machine* open a socket.

So: state shown, control not offered, reason stated on the page. R059 §5's test — *a
control that renders as operable and isn't would be the right-typed lie as a button* —
is asserted both on the rendered body and on the page a browser actually receives.

**The page also says what the switch does not stop.** From `killswitch`'s own docstring:
it does not stop policy-making, because nothing ratified can move while the switch
holds. An operator who reads ENGAGED and assumes ratification is blocked has the wrong
model of their own incident. Its rank was checked against `decision.py` — step 1, clamp
unconditional — not inferred from the name, per R058 §4.

### The budget arithmetic is not the obvious one

**A reservation is already written into `cap_counters`.** `caps._reserve_all` bumps the
counter at reserve time, so the counter is *consumed plus reserved*. Rendering it as
"consumed" would show **held money as money gone** — an operator reading a budget as
spent while it is still reclaimable, in the screen they open during an incident. So:

```
reserved = the deltas of reservations still `held`
consumed = counter − reserved
free     = limit − counter
```

Asserted three ways: the decomposition itself, that `consumed + reserved + free == limit`,
and that a release landing between the two reads clamps at zero rather than rendering
negative spend — *a view of a moving store, said as such.*

**An undeclared cap draws no bar at all.** A window with no limit is not a full bar or an
empty one; both state a proportion nobody declared. The counter is shown and the page
says why there is no bar. Conversely a **declared cap with no counter yet is shown at
zero** — omitting it would make a fresh deployment look as though it had no budgets.

Limits come from the **snapshot behind the pinned version** (R058 §1), not the live
tables, tested by writing a different cap straight into `policies` and asserting the bar
does not move. A bar measured against an unsnapshotted limit would draw a boundary the
engine is not enforcing.

### Three outcomes on the reservation deadline

Within deadline, past it, and **unreadable**. Unparseable is not "fine": a screen must
not answer a question it could not evaluate, so it renders `deadline unreadable` rather
than quietly counting as healthy.

### Read-only, both ways

`test_the_live_module_contains_no_write` scans the source — R059 §1's ruling that the
structural assertion is the fence — and `test_reading_the_live_page_over_http_changes_nothing`
drives eight requests through the server and compares the switch, the counters and the
audit row count before and after, which is the smoke.


## V3 — S4 History, with Q4 and Q6

`onedoor/studio/history.py` (read model), two routes, and the Q4/Q6 fixes R058 §8
assigned to this stage.

**Entries are numbered by the chain, not by the page.** `seq` is the sequence the row
was sealed with — the number `prev_hash`/`row_hash` link. Numbering by position in a
filtered listing would invent an ordinal that changes when a filter changes, so an
auditor quoting "entry 14" would be quoting the page. **A register's numbers belong to
the register.** Rows predating the chain render `unchained`, never `0`.

**Read-only, asserted against the source.** `test_the_history_module_contains_no_write`
scans the module for any write statement, because the property is that no write path
*exists* — a behavioural test only proves the paths it happened to take.

**No silent caps.** A page shows 50 and says how many matched.

**The digest labels were checked, not guessed.** E/I/T/V are evidence, instrument, trust
and verdict, read from `guardrail/digests.py`. A screen that captioned `t_digest` as
"target" — because the canary pillar uses T that way — would be confidently wrong in a
compliance product.

### The fifth filter R055 V3 asks for cannot be built — escalated as Q7

R055 V3 lists filters for *"time, action, verdict, policy version, key"*. Four are
columns. **The fifth is not recorded anywhere.** `onedoor.service` authenticates callers
with bearer API keys (`Authorization: Bearer`), but `audit.append` takes **no caller
identity** and `actions_audit` has **no column for one**. The ledger cannot say who
asked.

`source` is the nearest column and means something else — *how the request was built*
(scheduler, rule, llm, ui), which the model documents as *"informational only, never
affects the decision"*. Offering it as an actor filter would answer a question about
identity with a fact about provenance, so it is offered under its own name and the
missing filter is **stated on the page**: an absent capability that is silently omitted
reads as a capability that exists and found nothing.

Recording an actor is a **schema change**, which R055 constraint 1 freezes until Sept 12
— *"if any stage genuinely needs an engine change, STOP and escalate; do not land it
early"*. So: stopped, and escalated.

### Q4 — the `--faint` audit, by use

| use | must be read? | outcome |
|---|---|---|
| `th` — table headers | yes, they are the column labels | corrected |
| `.empty` — empty-state text | yes, it is the whole message | corrected |
| `.kv dt` — key labels | yes | corrected |
| `footer` — the loopback claim | yes, it is a product claim | corrected |
| `.tab.unbuilt` — a disabled tab | WCAG exempts inactive controls | **exemption available, not taken** |

`--faint` `#6e6152` → `#927e67`, **2.96 → 4.57:1**, hue held to **0.05°**. The exemption
was not taken because a disabled control that is also unreadable is bad twice, and
because the hierarchy that makes a disabled tab *look* disabled survives anyway: ink
13.24 > dim 6.04 > faint 4.57. Nothing was left at "matters slightly less".

The saturation assertion is now scoped to the state triple, with the reason recorded:
`--faint` is a near-neutral where 8-bit rounding trades hue against saturation, and
core's stated constraint is **hue**. Holding saturation instead would have moved the hue
24× further to protect a number nobody stated.

`test_chrome_text_clears_aa_and_the_one_gap_is_named` asserted the gap **in the failing
direction** so that fixing it would force the exception to be deleted. That is exactly
what happened.

### Q6 — the 404, in every channel

The detail route answers 404 for a rule absent from the version in force. **The first
fix was wrong and was caught before commit:** `raise HTTPException(404, detail=html)`
answers with `content-type: application/json` wrapping HTML — it fixed the status code
and broke the media type, moving the lie to a different header. It is now an
`HTMLResponse` with `status_code=404`. Both directions tested, including that a known
action still answers 200 and that the body is the page rather than a serialised error
object.

### Defect self-caught: a form that did not echo its own filter

Found by the served test. A filter value not among the ledger's choices vanished from
the form while still filtering the page — so a bookmarked filter whose rows had aged out
rendered as "any" over an empty register, and the emptiness read as *"no such decisions
ever"* instead of *"none match"*. The value is now echoed and marked `not in this
ledger`, with both directions tested. **A form that does not echo what it filtered on is
a page lying quietly.**

## Ruled by R057 — what changed

**Q1 approved, and the defect is core's.** The failing ratios are defects in the
approved mockup; *"accessibility is not a deviation from the design; inaccessibility
is."* The three state foregrounds are corrected — **and the correction is recorded
beside the vendored block, never edited into it**, so the palette the Studio renders can
still be diffed against the palette core approved. Each entry in `tokens.CORRECTIONS`
carries the measurement that forced it.

| token | mockup | corrected | on its chip |
|---|---|---|---|
| `--allow` | `#4f9e6b` | `#53a670` | 4.18 → **4.58:1** |
| `--review` | `#d07f3c` | `#d18240` | 4.45 → **4.58:1** |
| `--refuse` | `#c05548` | `#cc766b` | 3.33 → **4.58:1** |

Hue and saturation held (all three drift under 0.4°); backgrounds and brand untouched.
Target was 4.55 rather than 4.50 so a rounding difference in any checker cannot flip a
passing build.

**What the correction cost, disclosed per R057 §6.** The V1 ΔE floor of 15.0 does not
survive, and no choice of hex would have saved it — `--refuse` failed AA *because* it
was dark, and any red light enough to read converges with `--review` under tritanopia
and `--allow` under deuteranopia. Four searches were run (foreground-only, background
darkening, joint, saturation-free); the best reached 13.8, still under the floor and
only by darkening the refusal chip until it vanished into the page ground.

| pair | mockup | corrected |
|---|---|---|
| `--review` / `--refuse`, tritanopia | 15.1 | **2.5** |
| `--allow` / `--refuse`, deuteranopia | 18.0 | **6.5** |

**The floor is replaced rather than lowered.** Contrast decides whether a person can
read the word; ΔE decides whether they can tell two colours apart *when colour is the
only signal* — and colour is not the only signal here. `shell.chip()` renders a colour
**and a word**, always, and `test_no_state_is_signalled_by_colour_alone` holds that as a
property. That is what WCAG 1.4.1 actually requires and what a ΔE floor was only ever a
proxy for. Under normal vision a floor still binds (24.0, measured minimum 27.9), and
the dichromat matrix prints in CI so a future shrink shows up in a log rather than in
silence.

**A second gap, found by the same check and NOT fixed:** `--faint` on `--ground` is
**2.96:1**, below AA. It styles uppercase table headers at `.7rem/600`. Left uncorrected
because it was outside Q1's approved scope — *a token quietly widened past its ruling is
the drift the corrections layer exists to prevent* — and asserted in the failing
direction so that fixing it forces the exception to be deleted. **Asked as Q4 below.**

**The cursor, amended.** R057 §2 is right and delivery's read was too austere: R055 §3
mandates copy-on-click *and* permits "minimal inline JS", and V1 dropped a mandated
affordance to keep a rule core had not made. Copy-on-click returns as progressive
enhancement — `shell.COPY_SCRIPT` adds `copyable` in the same loop body that attaches
the handler, and returns early where no clipboard API exists, so **the cursor cannot
appear over an element that will not copy**. Nothing the server emits carries the class.
With scripting off the page is exactly what V1 shipped. Not escalated; implemented.

**`asserted`/`measured` promoted** to `studio.proposer.KINDS`, used by the skin and read
by the seal check, which no longer types any part of its vocabulary.

## Questions for core

**Q1, Q2 and Q3 are closed by R057.** Their outcomes are recorded above.

**Q4 — `--faint` fails AA too, and was left alone deliberately.** The contrast check
that R057 §5 put into CI found a second failure outside Q1's scope: `--faint` on
`--ground` is **2.96:1**, and it styles the uppercase table headers V2 is about to
render at `.7rem/600`. It is not a state colour, so the new token law does not reach it,
and correcting it under Q1's approval would be **widening a ruling past what was asked**
— the drift the corrections layer exists to prevent.

Proposal: lighten `--faint` to clear 4.5:1 on `--ground` (it needs roughly `#7f715f`),
hue held, as a second entry in `CORRECTIONS` citing this ruling. It is a header colour;
nothing about the ledger-room look depends on it being the faintest possible.

Meanwhile `test_chrome_text_clears_aa_and_the_one_gap_is_named` asserts the gap **in the
failing direction** — it fails if `--faint` ever starts passing — so whoever fixes it is
forced to delete the exception rather than leave a stale carve-out behind.

**Q4, Q5 and Q6 are closed by R058.** Q4 and Q6 landed in V3. Q5's two-voice layout lands
wherever the detail view next changes — V3 changed the detail *route*, not its body. The
plumbing is verified reachable: `proposer.Mention` links a description phrase to an action
type, and a ratification's `candidate_digest` **is** the proposal's `policy_digest`, so
`descriptions.records_for_policy` reaches the frozen words for a given rule with no new
stored pointer.

**Q8 — a pytest-internal failure seen once and not reproduced.** One gate run failed with
`KeyError: <_pytest.stash.StashKey object …>` from `_pytest/stash.py`, with no test
named. The immediately preceding and following full runs both passed (1104 passed, 9
skipped), as did a bare `pytest -q` in between; the gate is green on the committed tree.

Reported rather than swallowed, because a suite that fails once in three runs is a green
gate worth less than it looks. **Suspected but unproven:** the token tests call
`capsys.disabled()` to print the contrast and ΔE matrices R057 §5 requires in CI, and the
error came from pytest's capture stash. That is the documented API for the job, so this
is a suspicion and not a finding.

**Proposal if it recurs:** move the measurement printing out of the tests and into a
`pytest_terminal_summary` hook in `conftest.py`. That is where report output belongs, it
touches no per-test capture, and the numbers become part of the run's report rather than
incidental output — which is a better home for them regardless. Not done now: changing
the mechanism on one unreproduced flake would be treating a suspicion as a diagnosis, and
the current arrangement is what core ruled and can audit.

**Q7 is ruled by R059 §3 — and delivery's proposed shape was rejected, correctly.**

The interim rendering is approved as built: `source` under its own name, the missing
actor filter stated on the page.

**`actor_hash` over the bearer key fails "never digest secrets."** Core: *a hash of a
credential is an oracle* — anyone holding the key list, or guessing at weak keys, can
test candidates against exported audit rows, which ships a credential-checking service
inside every export. Delivery's instinct (*a raw key in a receipt is a credential in a
receipt*) was right and **stopped one step short: a digest of a credential is still a
function of the credential.**

**Ruled shape, for the `0.7.0` line after Sept 12:**

- a **non-secret `key_id`** assigned at key creation — assigned, stable, meaningless;
- `key_id` column on the key store, `actor_id` on `actions_audit`;
- **nothing derived from the secret ever touches a row** — revealing the ledger reveals
  which key acted, never anything about the key;
- **backfill nothing**: rows predating the column render an explicit `unattributed`
  marker, the same honesty `unchained` already established;
- **`audit.append` grows the parameter in the same change**, so no future row can be
  written without deciding what to put there;
- the History filter arrives with the column.

Not before the firing sequence ends.


**Q5 — `descriptions.py` cannot do what R055 V2 cites it for.** Detail above. V2 ships
`library.sentences()`, derived from the policy. The open question is whether the detail
view should *also* show the operator's frozen description where one exists, labelled as
a separate kind of claim. **Proposal:** yes, in V7 when the editor makes descriptions
reachable, under a heading that says whose words they are. Not now, because a third pane
on a two-pane screen with no way to author the content is a feature with nothing in it.

**Q6 — the detail route answers rather than 404s, and that is a wire-adjacent choice.**
`GET /policies/{unknown}` returns **200** with *"no policy exists in the version in
force, so this action is denied."* The reasoning: the route is valid and the answer is a
fact about the deployed system, where a 404 would say the page does not exist. It is a
Studio page and not an AADP surface, so no wire behaviour is involved — flagged because
it is the kind of decision that should be core's if it ever moves onto one.

**Transitional state, noted rather than hidden:** `/` and `/draft/{id}` still wear the
oneview canvas skin and do not show the shell chrome; V5 restyles them. So the tab bar
is present on the shell's routes and absent on the drafts pages until then. Stated here
because an operator meeting it should meet it in the ticket first.
