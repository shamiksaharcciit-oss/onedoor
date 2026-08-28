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

## Stage board

| | Stage | State |
|---|---|---|
| **P0** | F-G empty state, F-H database trap | **shipped** — `0.6.2` |
| **V1** | Shell: tokens, tabs, header, version banner | **built** |
| **V2** | S1 Policies | **built** |
| **V3** | S4 History · Q4 · Q6 | **built** |
| **V4** | S5 Live state | **built** |
| **V5** | S3 Drafts | next |
| **V6** | Re-evaluate under version — the flagship | held (premise verified, R056) |
| **V7** | S2 Editor | held |
| **V8** | S6 Verify + the law tests | held |

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
