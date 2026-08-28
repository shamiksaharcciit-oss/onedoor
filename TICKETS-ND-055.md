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
| **V2** | S1 Policies | next |
| **V3** | S4 History | held |
| **V4** | S5 Live state | held |
| **V5** | S3 Drafts | held |
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

**No `cursor:copy` on digests.** The note asks for `first-8…last-4` *"with
copy-on-click, full on hover"*. Two of three are free: truncation is arithmetic, and
the full value goes in `title` and `data-digest`. Copy-on-click needs JavaScript, and
this app runs none — so the cursor is not emitted. **V8(f) one layer down: a cursor
that says *copy* over an element that cannot copy is an overclaim rendered in CSS.**
*An affordance is a promise; do not render the promise before the thing.*

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

## Questions for core

**Q1 — the state chips fail WCAG AA, measured.** The approved palette's chip colours on
their own chip backgrounds, at the mockup's `font-size:.72rem; font-weight:600` (~11.5px
bold — **not** WCAG "large text", so 4.5:1 applies):

| | measured | AA |
|---|---|---|
| `--allow` on `--allow-bg` | **4.18:1** | fails |
| `--review` on `--review-bg` | **4.45:1** | fails |
| `--refuse` on `--refuse-bg` | **3.33:1** | fails |
| `--refuse` on `--ground` | **3.92:1** | fails |
| `--faint` on `--ground` | **2.96:1** | fails (table headers) |

The refusal chip is the worst of them, which is the wrong one to lose. Deviating from
the approved palette is an escalation, so this is asked rather than fixed. **Proposal:**
lighten the three state foregrounds until each clears 4.5:1 on its own background,
leaving hue and the brand tokens untouched — the ledger-room look is carried by the
ground and the gold, not by the chip's exact lightness. V1 does not depend on the
answer; **V2 is the first stage that renders a chip.**

**Q2 — the palette survives a colourblind check; here are the numbers.** The note asks
for state colours "colorblind-checked", so they were, under Viénot 1999 (CIE76 ΔE):

| pair | normal | protan | deutan | tritan |
|---|---|---|---|---|
| `--gold` / `--review` | 28.7 | 22.6 | **15.6** | 18.2 |
| `--review` / `--refuse` | 27.8 | 26.8 | 20.8 | **15.1** |
| `--allow` / `--refuse` | 79.3 | 19.1 | 18.0 | 70.2 |

Nothing collapses. The tightest pair is **brand-vs-state under deuteranopia** — exactly
the boundary §4 draws — so it is the one under a test floor (15.0, the measured value
rounded down). Reported because a passing check nobody sees the numbers of is a passing
check nobody can audit. **No action requested.**

**Q3 — a hand-typed word in a derived vocabulary.** The strengthened check derives its
state vocabulary from `studio.coverage`'s enumerations, so it cannot go stale. It cannot
do that for `asserted`/`measured`: those are literal class names in
`viewer/proposal.py`, declared nowhere, and R056 §4 requires `section.asserted`
migrated — so the check needed one hand-declared entry. **A vocabulary half-derived and
half-typed goes stale on the typed half.** Proposal: promote `asserted`/`measured` to
declared constants in `studio.proposer` so the check reads them like the rest. Small,
additive, and not urgent.

**Transitional state, noted rather than hidden:** `/` and `/draft/{id}` still wear the
oneview canvas skin and do not show the shell chrome; V5 restyles them. So the tab bar
is present on the shell's routes and absent on the drafts pages until then. Stated here
because an operator meeting it should meet it in the ticket first.
