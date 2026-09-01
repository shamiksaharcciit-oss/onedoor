# Dogfooding script — the pass that gates the `0.7.0` tag

**Which world you are in — currently answered, and it may change once before your pass.**

**As it stands: section I is NOT part of this pass.** The model-proposer track measured
0 of 11 against its own acceptance corpus on 2026-09-01 and does not ship in this release
on that result. There is no Propose tab to look for, and its absence is correct rather
than a fault. **Your block is the 60–75 minutes below.**

That answer can flip once, and only once. A fix is being attempted under three gates; if
all three are met before you start, you will be handed the **66–81 minute** version of this
script with section I included, and this paragraph will say so instead. **If nobody hands
you a different script, this one is the one to walk** — the fallback is the current state,
not a pending decision, so an unanswered question never leaves you guessing at the door.

**Block 60–75 minutes.** That is the honest envelope, and it is made of two parts:

- **45 minutes of walking** — every stop in sections A–H with nothing going wrong. That
  number is arithmetic, per-section, and asserted by a test.
- **15–30 minutes of findings** — expected, not feared. **Two or three findings is what
  success looks like for a pass like this**, and the time to write them down is part of
  the work rather than an overrun of it.

A budget that counted only the walking would be describing a pass that found nothing.

**If you run short of time: cut [SEE] stops, never [GATE] stops.** That rule is enforced
by a test on this document, and it is stated here so you know it before you need it.

**For Shamik, on a machine that has never run this.** This is the operator pass R066 §2
made a condition of the tag: no pass, no tag.

**How to use it.** Every stop has three lines — **Do**, **Expect**, **Ask**. Work down the
page. When what you see does not match **Expect**, that is a **finding**: write down what
you saw in your own words and keep going. Do not stop to diagnose.

> **Why the route is shaped like this.** It is not a tour of the screens. It builds state
> early and consumes it late — one draft is created in the editor, uploaded over, submitted
> through the API, ratified in the ceremony, replayed under two versions, and finally
> verified by a command that does not trust the Studio. **The seams are where F-A, F-G and
> F-H lived**, and none of them was a screen; each was a place where two screens met.

> **Quoted text is quoted for a reason.** Where a line below is in quotation marks, that
> exact sentence is a constant in the code, and `tests/studio/test_dogfooding_script.py`
> asserts this document still quotes it correctly. If a quoted sentence is *missing* from
> the screen, that is a finding — the words are load-bearing, not decoration.

**The walking budget is 45 minutes**, sections A–H. **Section I (Propose) is not in the
45** — see *What a second pass covers* at the end.

**Every stop is marked:** **[GATE]** stops must be walked for the tag; **[SEE]** stops are
worth your eyes but do not block.

---

## A · Arrival — 4 minutes

Two terminals. In the first:

```
python -m onedoor.studio --db onedoor.db --studio-db studio.db
```

Open `http://127.0.0.1:8787`.

**A1 [GATE] — the promise in the footer.**
**Do:** look at the bottom of the page.
**Expect:** "loopback only — nothing leaves this machine".
**Ask:** does anything on this page look like it came from the internet — a font, an icon,
a spinner? It should not. That sentence is a claim the code enforces at bind time.

**A2 [GATE] — the version banner.**
**Do:** look at the top strip.
**Expect:** either a version digest, or "no version in force", or a version with "not
ratified through this Studio". One of the three, never a blank.
**Ask:** does it say something, rather than showing an empty space? A blank here is the
single most likely thing to read as "still loading" when it is not.

**A3 [SEE] — the tabs.**
**Do:** read the tab bar.
**Expect:** Policies · Drafts · History · Live state · Verify. **No Propose tab**, unless
you configured a model endpoint before starting.
**Ask:** is anything there that you cannot click?

---

## B · Policies — 4 minutes

**B1 [GATE] — what the page claims to be.**
**Do:** open **Policies** and read the line under the heading.
**Expect:** "An action with no policy here is denied. This page lists what is permitted
and under what limits; it is not a list of what is blocked, because nothing needs to be
listed to be blocked."
**Ask:** could a reader mistake this page for a list of things that are blocked? That
misreading is the one it is written to prevent.

**B2 [SEE] — a rule's two voices.**
**Do:** click any action type.
**Expect:** the left pane says what the rule *does*, in sentences; the right pane is the
rule itself. If the rule came from a description someone wrote, a third block quotes them,
marked as their words.
**Ask:** do the plain-English sentences and the rule agree? If they disagree, the sentences
are wrong — they are derived from the rule, not from anyone's memory.

**B3 [GATE] — the header digest names the source.**
**Do:** note the version digest in the banner.
**Ask:** everything on this page should be the rules *behind that digest*, not whatever is
in the database right now. You cannot check that by looking — but if you later see this
page disagree with a version digest beside it, that is a serious finding.

---

## C · Author a policy three ways — 14 minutes

**This is the section that gates the tag.** The draft you make here is used by every
section after it.

### C1 · The editor — 5 minutes

**C1a [GATE] — make the draft.**
**Do:** **Drafts** → type `the pass draft` → *Open a draft*.
**Expect:** a draft page, pinned to the version in force.
**Ask:** does it say what it is pinned to?

**C1b [GATE] — edit a rule, and watch it check as you type.**
**Do:** open a rule in the draft. In the right-hand pane, change `"tier": 3` to
`"tier": 2` and pause — **do not save**.
**Expect:** within about a second, the validation below updates on its own, and the
refusal list gains a line about `compensating_command`.
**Ask:** did it update *without you saving*? That is the whole point of the track: nothing
the loader would refuse at boot should first be discovered at boot.

**C1c [GATE] — fix it and watch it clear.**
**Do:** add `"compensating_command": "payments.refund"` to the same pane. Pause.
**Expect:** the refusal disappears.
**Ask:** does the refusal list ever tell you something *is* wrong when it is not? A list
that cries wolf is worse than one that misses.

**C1d [SEE] — the two panes.**
**Do:** save from the raw pane and look at the guided form beside it.
**Expect:** the same values, in both, including decimals spelled the same way.
**Ask:** can you make the two panes disagree? If you can, that is a significant finding.

### C2 · Upload — 5 minutes

**C2a [GATE] — a file the loader refuses.**
**Do:** save this as `bad.yaml` and upload it on **Drafts** → *From a file*:

```
policies:
  - action_type: payments.transfer
    tier: 2
```

**Expect:** you get a **draft anyway**, and its page shows the refusal about
`compensating_command`, the stage "applying the per-rule rules", and a line number.
**Ask:** were you given the reasons, or handed your file back? Being handed your file back
is the behaviour this track replaced.

**C2b [GATE] — a file that will not parse at all.**
**Do:** upload a file containing `policies:` then a line reading `  - [unclosed`.
**Expect:** a refusal at the stage "reading the file", plus: "Checking stopped at this
stage. The stages after it did not run, so they found nothing because they were not asked
— not because there is nothing to find."
**Ask:** is it clear that the later checks *did not run*, rather than passing? Silence from
a check that never ran is the easiest thing on that page to misread.

**C2c [SEE] — a file that is not text at all.**
**Do:** upload any small image, renamed to `.yaml`.
**Expect:** a page saying the file could not be read, and explicitly **not** saying the
policy is invalid.
**Ask:** does it accuse your policy of anything? It should accuse only your file.

**C2d [GATE] — the honesty line.**
**Do:** look under any refusal list.
**Expect:** "These are the problems found, not all problems: the engine's validator stops
at the first failure in each rule, and defects that only appear when rules are read
together are invisible to a per-rule check."
**Ask:** does the page ever suggest the list is complete? It must not.

### C3 · The API — 4 minutes

In the second terminal.

**C3a [GATE] — read the draft you made in the browser.**
**Do:** `curl -s localhost:8787/api/v1/drafts` and find `the pass draft`; note its
`draft_id`.
**Expect:** the same draft, with `"state": "draft"` and the rules you edited.
**Ask:** is this the same object you were just looking at? The UI and the API are one
store — if they disagree, that is a serious finding.

**C3b [GATE] — ask the API what the loader thinks.**
**Do:** `curl -s localhost:8787/api/v1/drafts/<id>/validation`
**Expect:** two separate keys — `refusals` and `forecasts` — never one merged list.
**Ask:** could a program reading this mistake a forecast for a refusal?

**C3c [GATE] — submit it, and check that nothing was approved.**
**Do:** `curl -s -X POST localhost:8787/api/v1/drafts/<id>/submit`
**Expect:** `"state": "submitted"`, a `ceremony_url`, and: "A human has been asked to
ratify this draft. Nothing has been approved, no version pointer moved, and no receipt was
written. Ratification happens on the ceremony page."
**Ask:** reload **Policies**. Did anything change? It must not have. *Submitting is asking,
not approving.*

**C3d [SEE] — the API says what it is not.**
**Do:** `curl -s localhost:8787/api/v1/openapi.json` and find the description.
**Expect:** "The v1 API adds no approval route — ratification belongs to the human
ceremony. One legacy route (POST /draft/{id}/ratify), predating actor identity, still
serves; it records its approver as declared, never authenticated, and is retired with the
key_id work."
**Ask:** is that sentence true of what you have seen? It is written to be checkable, not
reassuring.

---

## D · The two lists — 5 minutes

**This stop exists because it is the easiest thing in the product to get wrong.**

**D1 [GATE] — a rule that loads and still misbehaves.**
**Do:** in your draft, give a rule a euro cap and **no** `cost_param` — add
`"caps": {"eur_day": "100"}` and make sure there is no `cost_param`.
**Expect:** it appears under **"Once in force, these rules will"** with the code
`cost_unknown` — and **not** under "The loader would refuse this".
**Ask:** which list is it in? **If it is in the refusal list, that is a finding and a
serious one:** the engine loads that rule happily and denies later, so calling it a boot
refusal would be the Studio lying about the engine.

**D2 [GATE] — the second list says what it is.**
**Do:** read the note above that list.
**Expect:** "These are not refusals: the loader accepts every rule below. They describe how
each rule will behave once it is in force, and each one names the reason code the engine
will record."
**Ask:** does every line there name a reason code? A forecast without one is unfalsifiable.

**D3 [SEE] — and it does not overclaim either.**
**Expect:** "Only the behaviours this check knows how to predict are listed. A rule with no
row here has not been shown to be free of surprises."
**Ask:** does the page ever imply the rule is *safe*? It should say only what it checked.

---

## E · The ceremony — 6 minutes

**E1 [GATE] — reading is not ratifying.**
**Do:** open the draft's *Review and ratify* page. Read it. Do **not** confirm yet. Then
open **Policies** in another tab.
**Expect:** nothing has changed.
**Ask:** did loading the page change anything? It must not — that is the entire reason
this is a page and not a button.

**E2 [GATE] — what it promises.**
**Expect:** "Ratifying applies these rules to the enforcer store and seals a receipt. There
is no un-ratify: to go back you ratify again, which is a new version and a new receipt.
Nothing that already happened under the old rules is changed by either."
**Ask:** does it say anywhere that this "cannot be undone", or call it "permanent" or
"irreversible"? **Those words would be a finding.** They are false, and false in the
direction that looks like caution.

**E3 [GATE] — ratify.**
**Do:** confirm, with a session note.
**Expect:** a receipt with a digest, and **Policies** now shows your rules.
**Ask:** does the receipt name who ratified? It names what you *typed* — it is declared,
not authenticated, and the product says so rather than pretending.

**E4 [SEE] — the diff you were shown.**
**Ask:** did the "would become" side match what is now in force?

---

## F · History and re-evaluation — 6 minutes

**F1 [GATE] — make a decision happen.**
**Do:** in the second terminal:

```
python -m onedoor.studio.walkthrough --db onedoor.db
```

**Expect:** it prints what it did.
**Ask:** nothing yet.

**F2 [GATE] — find it.**
**Do:** open **History**.
**Expect:** your decision, with a chain number.
**Ask:** if you filter the list, does the form *show* you the filter you applied? An
invisible filter turns "no rows" into a false statement about the world.

**F3 [GATE] — replay it under a different version.**
**Do:** open the entry, choose another version, and re-evaluate.
**Expect:** both versions named together, and a sentence saying this is what *would have*
happened — not what will.
**Ask:** is it obvious that nothing was re-executed? And if a version's rules cannot be
retrieved, does it say "not retrievable" rather than showing an empty policy set? **An
empty policy set replayed would return a confident "denied" that means nothing** — that
row is the feature's conscience.

---

## G · Verify — 4 minutes

**G1 [GATE] — the page built for a stranger.**
**Do:** **Verify** → open your receipt.
**Expect:** the method first, the answer last, and the two files offered for download.
**Ask:** could someone who distrusts you, and distrusts this software, check this claim
with what the page gives them?

**G2 [GATE] — check it without trusting the Studio.**
**Do:** save the two files and run:

```
python -m onedoor.studio.verify receipt.json snapshot.json
```

**Expect:** `verified`, exit `0`.
**Ask:** now corrupt one file — delete a character — and run it again. Does it say
`unreadable` rather than `failed`? **Telling you your receipt is bad when what is bad is
your download would be the worst error this page could make.**

---

## H · Live state — 2 minutes

**H1 [GATE] — the kill switch you cannot throw here.**
**Do:** open **Live state**.
**Expect:** the switch's state shown, **no button**, and a stated reason why this process
does not offer one.
**Ask:** does anything look clickable that is not? A control that renders as operable and
is not would be a finding.

**H2 [SEE] — the budget bars.**
**Ask:** does a cap with no declared limit draw an empty bar, or no bar at all? It should
draw nothing and say why — a bar needs a denominator.

---

## I · Propose — **not in the 45 minutes**

**Only if a model endpoint was configured before the Studio started.** If it was not, there
is no **Propose** tab, and that absence is itself correct — check it and move on.

**I1 [GATE, if T3 ships] — the capability sentence.**
**Expect:** "drafts proposed by a model, ratified by you".
**Ask:** does any surface anywhere suggest the model *writes* or *approves* policy? That
would be a finding.

**I2 [GATE, if T3 ships] — a description in, a draft out.**
**Do:** describe something in plain words, including one thing you expect it to miss.
**Expect:** a draft, with "Where this draft came from" naming the model and a prompt
digest, and a section headed "Mentioned, and not covered by any rule" quoting **your**
words.
**Ask:** is the gap section quoting *you*, or paraphrasing the model? It must quote you.

**I3 [GATE, if T3 ships] — a generation the loader refuses.**
**Do:** if you can, prompt it toward something invalid.
**Expect:** the refusal *and* the model's raw output, side by side, with nothing repaired.
**Ask:** was anything silently fixed to make it parse?

---

## The honest time budget

| Section | Minutes | Gates the tag |
|---|---|---|
| A · Arrival | 4 | yes |
| B · Policies | 4 | yes |
| C · Author three ways | 14 | yes |
| D · The two lists | 5 | yes |
| E · The ceremony | 6 | yes |
| F · History and re-evaluation | 6 | yes |
| G · Verify | 4 | yes |
| H · Live state | 2 | yes |
| **Total** | **45** | |
| I · Propose | +6 | only if T3 ships |

**The 45 is the walking half, and it is a floor rather than a budget.** It assumes
nothing goes wrong and no finding is investigated. **Every finding costs time the walking
number does not contain** — writing one down is a minute, and the first usually prompts a
second look at the screen before it.

So the envelope at the top of this page is **60–75 minutes** (66–81 if section I is in),
and the 15–30 minutes of findings in it is an **expectation, not a risk**: this pass
exists to produce findings, and a schedule that leaves no room for the thing the activity
is for has budgeted for failure and called it success.

**If time runs short, the order to cut in:** H2, B2, E4, C1d, C2c — the **[SEE]** stops.
Every **[GATE]** stop should be walked before the tag; they are the ones covering a seam,
a promise the product makes in words, or a failure mode this build was written to prevent.

## What a second pass covers

- **Section I** in full, once the T3 decision is made. It is out of the 45 because T3's
  own gate (a benchmark with published misses) is unresolved, so its screens may not ship.
- **Anything a finding opened.** A finding is a reason to look harder at that area, and
  looking harder is a second pass, not an overrun of this one.
- **A second operator.** Every screen here has been read by the person who wrote it. The
  three findings that shaped this Studio most — F-A, F-G, F-H — came from someone using it
  and saying what happened.

## What counts as a finding

Anything that does not match **Expect**. Also, and worth as much:

- a sentence you had to read twice
- a screen where you were not sure what you were looking at
- a moment you expected something to happen and it did not
- **anything that felt wrong even if it was technically correct**

Write it in your own words. Do not translate it into our vocabulary — the translation is
our job, and something is usually lost in it.

Integrity: sha256(body) = 698a838994483756bea4ac28c434ec06a2ab0dd346e841cc0c7dbc8aeefb0536
