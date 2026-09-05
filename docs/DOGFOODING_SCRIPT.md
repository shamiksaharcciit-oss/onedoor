# Dogfooding script — the pass that gates the `0.7.0` tag

**Regenerated after R086; A0 patched after R088.** The first pass on this script reached
section C in about forty minutes and could not continue: it never seeded the store, so
C1b had no rule to open, and a fenced YAML block copied by hand picked up its own
language tag as the file's first line. Both are script defects, fixed then — not
patched, rewritten. Four product defects the same pass found are fixed separately, in
the Studio itself; this script now describes the product as it actually behaves.

The **second** pass, on the regenerated script, reached A0 and reused a `pass.db` a
dry-run had already left on disk sixteen hours earlier — "purpose-made store" failed
**silently**, and operator suspicion was the only detector (R088 §3, F-S1). A0 now
removes any `pass*.db*` and `pass-policies.yaml` already on disk before it seeds, and
says so, rather than reusing them without a word.

**Which world you are in — currently answered, and it may change once before your pass.**

**As it stands: section I is NOT part of this pass.** The model-proposer track measured
0 of 11 against its own acceptance corpus on 2026-09-01 and does not ship in this release
on that result. There is no Propose tab to look for, and its absence is correct rather
than a fault. **Your block is the 65–80 minutes below.**

That answer can flip once, and only once. A fix is being attempted under three gates; if
all three are met before you start, you will be handed the **71–86 minute** version of this
script with section I included, and this paragraph will say so instead. **If nobody hands
you a different script, this one is the one to walk** — the fallback is the current state,
not a pending decision, so an unanswered question never leaves you guessing at the door.

**Block 65–80 minutes.** That is the honest envelope, and it is made of two parts:

- **50 minutes of walking** — every stop in sections A–H with nothing going wrong. That
  number is arithmetic, per-section, and asserted by a test.
- **15–30 minutes of findings** — expected, not feared. **Two or three findings is what
  success looks like for a pass like this**, and the time to write them down is part of
  the work rather than an overrun of it.

A budget that counted only the walking would be describing a pass that found nothing.

**If you run short of time: cut [SEE] stops, never [GATE] stops.** That rule is enforced
by a test on this document, and it is stated here so you know it before you need it.

**If a [GATE] stop does not match Expect, that is a finding: write down what you saw and
continue** — a mismatched Expect is not the same thing as being unable to proceed. Every
[GATE] stop's own marker says which of the two applies to it: **most say "note the
finding and continue"**, because the pass exists to collect findings and one stop reading
wrong does not stop the walk. **A few say what to skip**, because a small number of stops
build state the rest of the pass depends on — those are named, not guessed at, so the
question never has to come back up to whoever is running the pass. It came up three times
on the first attempt at this script; it should not need to again.

**For Shamik, on a machine that has never run this.** This is the operator pass R066 §2
made a condition of the tag: no pass, no tag. It runs against a store this script creates
— `pass.db` / `pass-studio.db` — never against whatever a previous pass or the README
quickstart left behind. A re-walk from section A is deterministic because of that.

**How to use it.** Every stop has three lines — **Do**, **Expect**, **Ask**. Work down the
page. When what you see does not match **Expect**, that is a **finding**: write down what
you saw in your own words and keep going unless the stop's own marker tells you to skip
ahead. Do not stop to diagnose.

> **Why the route is shaped like this.** It is not a tour of the screens. It builds state
> early and consumes it late — one draft is created in the editor, uploaded over, submitted
> through the API, ratified in the ceremony, replayed under two versions, and finally
> verified by a command that does not trust the Studio. **The seams are where F-A, F-G and
> F-H lived**, and none of them was a screen; each was a place where two screens met.

> **Quoted text is quoted for a reason.** Where a line below is in quotation marks, that
> exact sentence is a constant in the code, and `tests/studio/test_dogfooding_script.py`
> asserts this document still quotes it correctly. If a quoted sentence is *missing* from
> the screen, that is a finding — the words are load-bearing, not decoration.

**The walking budget is 50 minutes**, sections A–H. **Section I (Propose) is not in the
50** — see *What a second pass covers* at the end.

**Every stop is marked:** **[GATE]** stops must be walked for the tag; **[SEE]** stops are
worth your eyes but do not block. Each **[GATE]** marker also says what to do if you
cannot complete it at all — see the paragraph above.

**Files this pass creates**, all at the repo root, all disposable: `pass.db`,
`pass-studio.db`, `pass-policies.yaml`, `bad.yaml`, `broken.yaml`. None of them is
committed; none of them is read by anything outside this pass. **A0 removes the first
three before it seeds them fresh** — a leftover from a previous run is never reused
silently (F-S1); it is deleted, out loud, before this run writes its own.

---

## A · Arrival — 6 minutes

**Two terminals, both open before A0.**

- **Terminal 1** runs the seed commands once, then starts the Studio server and stays on
  it for the whole pass.
- **Terminal 2** is idle until section C3 and section F — it runs the API's `curl`
  commands and the walkthrough command. Open it now so you are not hunting for a second
  terminal mid-pass.

**A0 [GATE — if blocked, stop the pass here; nothing below can be walked without a
seeded store] — remove any leftover pass files, then seed a purpose-made store.**
**Do:** in the first terminal, from the repo root. **"Purpose-made" means made by THIS
run** — a `pass.db`, `pass-studio.db` or `pass-policies.yaml` a previous dry-run, a
previous pass, or a previous session left behind is exactly as ambient as `onedoor.db`,
and reusing one silently is F-S1 (R088 §3): the block below removes all three before
anything is written, so the removal is never silent and the seed that follows is never
a reuse. **On Windows, a file a running Studio server still has open cannot be
removed** (R090 §5) — the block below detects that and stops on its own rather than
seeding on top of files it failed to clear, which would resurrect the exact silent
contamination F-S1 exists to kill.

Windows (PowerShell):

```
$locked = @()
foreach ($f in 'pass.db','pass.db-wal','pass.db-shm','pass-studio.db','pass-studio.db-wal','pass-studio.db-shm','pass-policies.yaml') {
  if (Test-Path $f) {
    try { Remove-Item -Force $f -ErrorAction Stop } catch { $locked += $f }
  }
}
if ($locked) {
  Write-Host "pass files are locked by a running process; stop the Studio and re-run: $($locked -join ', ')"
} else {
  Write-Host "removed any leftover pass.db / pass-studio.db / pass-policies.yaml"
  Copy-Item onedoor\templates\payments\policies.yaml pass-policies.yaml
  python -c "from onedoor.store.db import Database; from onedoor.guardrail import policy_loader as pl; db = Database('pass.db'); db.init(); conn = db.connect(); n = pl.load_file(conn, 'pass-policies.yaml'); v = pl.record_snapshot(conn); print(f'{n} policies loaded'); print(f'version digest: {v}')"
  python -m onedoor.studio --db pass.db --studio-db pass-studio.db
}
```

macOS/Linux (POSIX shell):

```
rm -f pass.db pass.db-wal pass.db-shm pass-studio.db pass-studio.db-wal pass-studio.db-shm pass-policies.yaml
echo "removed any leftover pass.db / pass-studio.db / pass-policies.yaml"
cp onedoor/templates/payments/policies.yaml pass-policies.yaml
python -c "from onedoor.store.db import Database; from onedoor.guardrail import policy_loader as pl; db = Database('pass.db'); db.init(); conn = db.connect(); n = pl.load_file(conn, 'pass-policies.yaml'); v = pl.record_snapshot(conn); print(f'{n} policies loaded'); print(f'version digest: {v}')"
python -m onedoor.studio --db pass.db --studio-db pass-studio.db
```

**On POSIX, this stop does not apply**: `rm` can unlink a file another process still has
open (the inode persists until the last handle closes), so the same lock does not block
removal there — the block above stays unconditional on purpose.

**Expect:** if a prior Studio is still running against these files, the PowerShell block
prints "pass files are locked by a running process; stop the Studio and re-run" and
**does nothing else** — close that terminal (or press Ctrl-C in it) and run this block
again. Otherwise it prints "removed any leftover pass.db / pass-studio.db /
pass-policies.yaml" **every time**, whether or not anything was actually there to
remove — that line is not a report of what it found, it is a statement of what the
pass now guarantees: whatever seeds next did not inherit anything. The next two lines
print `6 policies loaded` and a `version digest: ` line carrying a 64-character hex
value, computed from what THIS run just loaded. The last command starts the server and
does not return — leave it running in this terminal and open `http://127.0.0.1:8787`.
**Ask:** policies enter a store only through this loader or the decision service's own
startup, never through the Studio — the Studio reads and ratifies and never loads. That
is why the seed step exists and why it runs before the server does anything. And: is
this genuinely the first thing that has touched `pass.db` today? If a prior attempt at
this pass is still running in another terminal, this removal will fight it for the
file — close that terminal first.

**A1 [GATE — if blocked, note the finding and continue] — the promise in the footer.**
**Do:** look at the bottom of the page.
**Expect:** "loopback only — nothing leaves this machine".
**Ask:** does anything on this page look like it came from the internet — a font, an icon,
a spinner? It should not. That sentence is a claim the code enforces at bind time.

**A2 [GATE — if blocked, note the finding and continue] — the version banner.**
**Do:** look at the top strip.
**Expect:** `in force <digest> · never ratified · 6 policies · 2 effects · loopback only`
— A0 recorded a version and nothing has ratified it through the Studio yet, so this is
not "one of three possible states" the way it would be on an unknown store; it is the
one state A0 produced, and it should read exactly that.
**Ask:** does the policy count here match the `6 policies loaded` line from A0? If it
does not, the two stores disagree about what was loaded.

**A3 [SEE — if blocked, note the finding and continue] — the tabs.**
**Do:** read the tab bar.
**Expect:** Policies · Drafts · History · Live state · Verify. **No Propose tab**, unless
you configured a model endpoint before starting.
**Ask:** is anything there that you cannot click?

---

## B · Policies — 4 minutes

**B1 [GATE — if blocked, note the finding and continue] — what the page claims to be.**
**Do:** open **Policies** and read the line under the heading.
**Expect:** "An action with no policy here is denied. This page lists what is permitted
and under what limits; it is not a list of what is blocked, because nothing needs to be
listed to be blocked."
**Ask:** could a reader mistake this page for a list of things that are blocked? That
misreading is the one it is written to prevent.

**B2 [SEE — if blocked, note the finding and continue] — a rule's two voices.**
**Do:** click **`payments.transfer`**.
**Expect:** the left pane says what the rule *does*, in sentences; the right pane is the
rule itself. If the rule came from a description someone wrote, a third block quotes them,
marked as their words.
**Ask:** do the plain-English sentences and the rule agree? If they disagree, the sentences
are wrong — they are derived from the rule, not from anyone's memory.

**B3 [GATE — if blocked, note the finding and continue] — the header digest names the
source.**
**Do:** note the version digest in the banner.
**Ask:** everything on this page should be the rules *behind that digest*, not whatever is
in the database right now. You cannot check that by looking — but if you later see this
page disagree with a version digest beside it, that is a serious finding.

---

## C · Author a policy three ways — 16 minutes

**This is the section that gates the tag.** The draft you make here is used by every
section after it.

### C1 · The editor — 7 minutes

**C1a [GATE — if blocked, skip C1b–C1d, D and E, note them not reached, and continue at
C2] — make the draft.**
**Do:** **Drafts** → type `the pass draft` → *Open a draft*.
**Expect:** a draft page, pinned to the version in force.
**Ask:** does it say what it is pinned to?

**C1b [GATE — if blocked, note the finding and continue] — edit a rule, and watch it
check as you type.**
**Do:** open **`payouts.schedule`** — the pack's only tier-3 rule, which is why it is the
one to open: this stop needs to start from a rule that is not already auto-executing. In
the right-hand pane, change `"tier": 3` to `"tier": 2` and pause — **do not save**.
**Expect:** within about a second, the validation below updates on its own, and the
refusal list gains a line about `compensating_command`.
**Ask:** did it update *without you saving*? That is the whole point of the track: nothing
the loader would refuse at boot should first be discovered at boot.

**C1c [GATE — if blocked, note the finding and continue] — fix it, twice, and watch it
clear identically both times.**
**Do:** still in `payouts.schedule`, add `"compensating_command": "payments.refund"` to
the pane and pause. `payments.refund` names no action type in this pack — it does not
exist.
**Expect:** the refusal disappears anyway.
**Do:** now change the value to `"payments.reverse"` — a real action type in this pack —
and pause again.
**Expect:** the refusal disappears identically. Nothing about the second attempt reads as
more correct than the first, because the check that cleared both is
`not policy.compensating_command` in `onedoor/guardrail/policy_loader.py` — truthiness
only. Neither string is resolved against the policy set, at load time or at decision
time; that gap is tracked as `ND-057` in `BACKLOG.md` and is not fixed in this release.
**Do:** save from the raw pane. This is the one real, saved change this section makes —
everything in C1b and up to here was live-checked and never written.
**Expect:** the draft's own page now shows `payouts.schedule` at tier 2 with this
reversal, and the Changes panel names it. **Section E ratifies this change; section F3
replays it against the version it produces.** If you skip this save, C leaves the draft
identical to what is already in force — E3 becomes a no-op with nothing to ratify, and
F3 has no second version to replay against (F-S3). This save is why F3 is reachable.
**Ask:** would you have guessed the earlier live-checking never wrote anything, from the
page alone? This stop exists because the answer is no — and because the list never
tells you something *is* wrong when it is not, which is a different, narrower promise
than "this reversal exists."

**C1d [SEE — if blocked, note the finding and continue] — the two panes, on a rule that
actually has decimals.**
**Do:** open **`payments.transfer`** — the pack's only rule with decimal caps and bounds
(`500.00`, `5000.00`, `0.01`, `2000.00`); `payouts.schedule` has none, so checking this on
it could not fail. Save from the raw pane and look at the guided form beside it.
**Expect:** the same values in both, decimals spelled the same way.
**Ask:** can you make the two panes disagree? If you can, that is a significant finding.

### C2 · Upload — 5 minutes

**C2a [GATE — if blocked, note the finding and continue] — a file the loader refuses.**
**Do:** write the file with an exact command — do not copy the block below by hand. A
fence's language tag becoming the file's first line is what sent the first attempt at
this script forty minutes sideways.

Windows (PowerShell):

```
@'
policies:
  - action_type: payments.transfer
    tier: 2
'@ | Set-Content -NoNewline bad.yaml
```

macOS/Linux (POSIX shell):

```
cat > bad.yaml <<'EOF'
policies:
  - action_type: payments.transfer
    tier: 2
EOF
```

Upload `bad.yaml` on **Drafts** → *From a file*.
**Expect:** you get a **draft anyway**, and its page shows the refusal about
`compensating_command`, the stage "applying the per-rule rules", and a line number.
**Ask:** were you given the reasons, or handed your file back? Being handed your file back
is the behaviour this track replaced.

**C2b [GATE — if blocked, note the finding and continue] — a file that will not parse at
all.**
**Do:** write this one the same way:

Windows (PowerShell):

```
@'
policies:
  - [unclosed
'@ | Set-Content -NoNewline broken.yaml
```

macOS/Linux (POSIX shell):

```
cat > broken.yaml <<'EOF'
policies:
  - [unclosed
EOF
```

Upload `broken.yaml`.
**Expect:** a refusal at the stage "reading the file", plus: "Checking stopped at this
stage. The stages after it did not run, so they found nothing because they were not asked
— not because there is nothing to find."
**Ask:** is it clear that the later checks *did not run*, rather than passing? Silence from
a check that never ran is the easiest thing on that page to misread.

**C2c [SEE — if blocked, note the finding and continue] — a file that is not text at
all.**
**Do:** upload any small image, renamed to `.yaml`.
**Expect:** a page saying the file could not be read, and explicitly **not** saying the
policy is invalid.
**Ask:** does it accuse your policy of anything? It should accuse only your file.

**C2d [GATE — if blocked, note the finding and continue] — the honesty line.**
**Do:** look under any refusal list.
**Expect:** "These are the problems found, not all problems: the engine's validator stops
at the first failure in each rule, and defects that only appear when rules are read
together are invisible to a per-rule check."
**Ask:** does the page ever suggest the list is complete? It must not.

### C3 · The API — 4 minutes

In the second terminal — open since section A0.

**C3a [GATE — if blocked, note the finding and continue] — read the draft you made in
the browser.**
**Do:**

Windows (PowerShell):

```
curl.exe -s localhost:8787/api/v1/drafts
```

macOS/Linux (POSIX shell):

```
curl -s localhost:8787/api/v1/drafts
```

Find `the pass draft`; note its `draft_id`. (`curl` in PowerShell 5.1 is an alias for
`Invoke-WebRequest` and `-s` throws — `curl.exe` reaches the real binary.)
**Expect:** the same draft, with `"state": "draft"` and the rules you edited.
**Ask:** is this the same object you were just looking at? The UI and the API are one
store — if they disagree, that is a serious finding.

**C3b [GATE — if blocked, note the finding and continue] — ask the API what the loader
thinks.**
**Do:**

Windows (PowerShell):

```
curl.exe -s localhost:8787/api/v1/drafts/<id>/validation
```

macOS/Linux (POSIX shell):

```
curl -s localhost:8787/api/v1/drafts/<id>/validation
```

**Expect:** two separate keys — `refusals` and `forecasts` — never one merged list.
**Ask:** could a program reading this mistake a forecast for a refusal?

**C3c [GATE — if blocked, note the finding and continue] — submit it, and check that
nothing was approved.**
**Do:**

Windows (PowerShell):

```
curl.exe -s -X POST localhost:8787/api/v1/drafts/<id>/submit
```

macOS/Linux (POSIX shell):

```
curl -s -X POST localhost:8787/api/v1/drafts/<id>/submit
```

**Expect:** `"state": "submitted"`, a `ceremony_url`, and: "A human has been asked to
ratify this draft. Nothing has been approved, no version pointer moved, and no receipt was
written. Ratification happens on the ceremony page."
**Ask:** reload **Policies**. Did anything change? It must not have. *Submitting is asking,
not approving.*

**C3d [SEE — if blocked, note the finding and continue] — the API says what it is not.**
**Do:**

Windows (PowerShell):

```
curl.exe -s localhost:8787/api/v1/openapi.json
```

macOS/Linux (POSIX shell):

```
curl -s localhost:8787/api/v1/openapi.json
```

Find the description.
**Expect:** "The v1 API adds no approval route — ratification belongs to the human
ceremony. One legacy route (POST /draft/{id}/ratify), predating actor identity, still
serves; it records its approver as declared, never authenticated, and is retired with the
key_id work."
**Ask:** is that sentence true of what you have seen? It is written to be checkable, not
reassuring.

---

## D · The two lists — 5 minutes

**This stop exists because it is the easiest thing in the product to get wrong.**

**D1 [GATE — if blocked, note the finding and continue] — a rule that loads and still
misbehaves.**
**Do:** in your draft, give a rule a euro cap and **no** `cost_param` — add
`"caps": {"eur_day": "100"}` and make sure there is no `cost_param`.
**Expect:** it appears under **"Once in force, these rules will"** with the code
`cost_unknown` — and **not** under "The loader would refuse this".
**Ask:** which list is it in? **If it is in the refusal list, that is a finding and a
serious one:** the engine loads that rule happily and denies later, so calling it a boot
refusal would be the Studio lying about the engine.

**D2 [GATE — if blocked, note the finding and continue] — the second list says what it
is.**
**Do:** read the note above that list.
**Expect:** "These are not refusals: the loader accepts every rule below. They describe how
each rule will behave once it is in force, and each one names the reason code the engine
will record."
**Ask:** does every line there name a reason code? A forecast without one is unfalsifiable.

**D3 [SEE — if blocked, note the finding and continue] — and it does not overclaim
either.**
**Expect:** "Only the behaviours this check knows how to predict are listed. A rule with no
row here has not been shown to be free of surprises."
**Ask:** does the page ever imply the rule is *safe*? It should say only what it checked.

---

## E · The ceremony — 6 minutes

**E1 [GATE — if blocked, note the finding and continue] — reading is not ratifying.**
**Do:** open the draft's *Review and ratify* page. Read it. Do **not** confirm yet. Then
open **Policies** in another tab.
**Expect:** nothing has changed.
**Ask:** did loading the page change anything? It must not — that is the entire reason
this is a page and not a button.

**E2 [GATE — if blocked, note the finding and continue] — what it promises.**
**Expect:** "Ratifying applies these rules to the enforcer store and seals a receipt. There
is no un-ratify: to go back you ratify again, which is a new version and a new receipt.
Nothing that already happened under the old rules is changed by either."
**Ask:** does it say anywhere that this "cannot be undone", or call it "permanent" or
"irreversible"? **Those words would be a finding.** They are false, and false in the
direction that looks like caution.

**E3 [GATE — if blocked, skip G, note it not reached, and continue at F or H] — ratify.**
**Do:** confirm, with a session note.
**Expect:** a receipt with a digest, and **Policies** now shows your rules.
**Ask:** does the receipt name who ratified? It names what you *typed* — it is declared,
not authenticated, and the product says so rather than pretending.

**E4 [SEE — if blocked, note the finding and continue] — the diff you were shown.**
**Ask:** did the "would become" side match what is now in force?

---

## F · History and re-evaluation — 6 minutes

**F1 [GATE — if blocked, note the finding and continue] — make a decision happen.**
**Do:** in the second terminal:

```
python -m onedoor.studio.walkthrough --db pass.db
```

**Expect:** `payments.transfer: denied (bounds)`. That is not a bug: the walkthrough
sends one parameter (`amount_eur`), and this pack's `payments.transfer` requires
`amount_eur` **and** `destination_account`. The walkthrough exists to put one decision in
front of you for History to show, not to satisfy every pack's bounds.
**Ask:** nothing yet.

**F2 [GATE — if blocked, note the finding and continue] — find it.**
**Do:** open **History**.
**Expect:** your decision, denied, with a chain number **or** `unchained` — chaining is
opt-in and periodic, so the newest row legitimately carries neither yet. `unchained` is
correct here, not a finding; the product is being honest about a state it has not
reached, the same honesty the `absent` anchor state carries (R089 §2, F-S2).
**Ask:** if you filter the list, does the form *show* you the filter you applied? An
invisible filter turns "no rows" into a false statement about the world.

**F3 [GATE — if blocked, note the finding and continue] — replay it under a different
version.**
**Do:** open the entry, choose the version from before you ratified in section E, and
re-evaluate.
**Expect:** both versions named together, and a sentence saying this is what *would have*
happened — not what will.
**Ask:** is it obvious that nothing was re-executed? And if a version's rules cannot be
retrieved, does it say "not retrievable" rather than showing an empty policy set? **An
empty policy set replayed would return a confident "denied" that means nothing** — that
row is the feature's conscience.

---

## G · Verify — 4 minutes

**G1 [GATE — if blocked, note the finding and continue] — the page built for a
stranger.**
**Do:** **Verify** → open your receipt from section E.
**Expect:** the method first, the answer last, and a **Download** link on both the
`receipt.json` and `snapshot.json` panels.
**Ask:** could someone who distrusts you, and distrusts this software, check this claim
with what the page gives them? Before this release the only path to the bytes was
select-and-paste out of the panel, which risks a byte and a false `failed` on a sound
receipt — R089 F-V1. The links are why that question now has a real answer.

**G2 [GATE — if blocked, note the finding and continue] — check it without trusting the
Studio.**
**Do:** click **Download** on both panels — not select-and-paste, the download gives
you the exact stored bytes — then, from the folder they landed in, run:

```
python -m onedoor.studio.verify receipt.json snapshot.json
```

**Expect:** `verified`, exit `0`.
**Ask:** two separate corruptions, on the files you downloaded — not on hand-typed or
pasted content, which would test your transcription rather than the verifier:

- **Truncate `receipt.json`** — delete its last few characters, so it is no longer
  parseable — and run the command again. **Expect `unreadable`, exit `2`.** A receipt
  the verifier cannot even read is a check that never ran.
- **Restore `receipt.json`, then change one digit inside `snapshot.json`** (it is
  still valid JSON — the change just makes it say something different) and run the
  command again. **Expect `failed`, exit `1`, naming the hash it actually got.** The
  verifier never parses the snapshot; it hashes the bytes and compares. A readable
  file whose bytes hash elsewhere is exactly what tampering looks like, and that is
  `failed`, not `unreadable` — the two corruptions land on opposite outcomes because
  they land on different halves of what the check does, and a script that expected
  `unreadable` from the snapshot corruption (an earlier version of this stop did)
  would have been asking you to watch the wrong number.

---

## H · Live state — 2 minutes

**H1 [GATE — if blocked, note the finding and continue] — the kill switch you cannot
throw here.**
**Do:** open **Live state**.
**Expect:** the switch's state shown, **no button**, and a stated reason why this process
does not offer one.
**Ask:** does anything look clickable that is not? A control that renders as operable and
is not would be a finding.

**H2 [SEE — if blocked, note the finding and continue] — the budget bars.**
**Ask:** does a cap with no declared limit draw an empty bar, or no bar at all? It should
draw nothing and say why — a bar needs a denominator.

---

## I · Propose — **not in the 50 minutes**

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
| A · Arrival | 6 | yes |
| B · Policies | 4 | yes |
| C · Author three ways | 17 | yes |
| D · The two lists | 5 | yes |
| E · The ceremony | 6 | yes |
| F · History and re-evaluation | 6 | yes |
| G · Verify | 4 | yes |
| H · Live state | 2 | yes |
| **Total** | **50** | |
| I · Propose | +6 | only if T3 ships |

**The 50 is the walking half, and it is a floor rather than a budget.** It assumes
nothing goes wrong and no finding is investigated. **Every finding costs time the walking
number does not contain** — writing one down is a minute, and the first usually prompts a
second look at the screen before it.

So the envelope at the top of this page is **65–80 minutes** (71–86 if section I is in),
and the 15–30 minutes of findings in it is an **expectation, not a risk**: this pass
exists to produce findings, and a schedule that leaves no room for the thing the activity
is for has budgeted for failure and called it success.

**If time runs short, the order to cut in:** H2, B2, E4, C1d, C2c — the **[SEE]** stops.
Every **[GATE]** stop should be walked before the tag; they are the ones covering a seam,
a promise the product makes in words, or a failure mode this build was written to prevent.

## What a second pass covers

- **Section I** in full, once the T3 decision is made. It is out of the 50 because T3's
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

Integrity: sha256(body) = 0a158be9f9bf3075dcb70969e35ab80455270888380b6850f6cba76fc09a1dd9
