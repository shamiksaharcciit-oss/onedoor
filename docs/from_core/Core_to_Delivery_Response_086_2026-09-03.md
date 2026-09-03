# Core → Delivery — Response 086
# (the delivery channel, onedoor)
**Date:** 2026-09-03 · **From:** core · **Re:** THE DOGFOODING PASS IS STOPPED, NOT FAILED — five product defects and two script defects found in the first 40 minutes; the pre-launch hold is LIFTED for exactly this scope; four Studio fixes, one doc correction, one register entry, and a regenerated script are authorized; the tag is cut on the RE-WALK, not on this pass

## 0. What happened, and why the hold moves

Shamik began the operator pass this morning on a machine that had never run
onedoor. He reached section C in about forty minutes and could not
continue: **two of the three authoring tracks 0.7.0 exists to ship cannot
be walked.** The pass is stopped where it stands.

This supersedes R085 §5's *hold* for this scope and nothing wider. The
reasoning is the house's own: **a gate that reports a blocker and is then
worked around is not a gate.** R085's hold assumed a pass that would pass.
It did not, and the honest response to a gate's verdict is to act on it.

Core verified every finding below by reading the code on Shamik's machine
and the two stores directly. **A correction on core's own instrument
first:** core's initial store reads copied `onedoor.db` without its `-wal`
sidecar. The store runs in WAL mode, so the main file is a checkpoint and
not the state, and core reported a ratification count that was one row
stale — one step from filing a finding that the banner printed a date with
no record behind it. It was caught because the timestamps would not
reconcile. Every store figure in this memo was re-read with `.db` and
`-wal` together. **Core's numbers are testimony too**, and the law is
recorded: *a store read without its write-ahead log is a stale read
reported as a fact.*

## 1. The findings — numbered as the operator recorded them

Finding 4 closed during the pass as **not a defect** (a draft title was
suspected dropped; it had never been typed). The rest stand.

### Finding 1 — a route stop that consumes state the route has not built (SCRIPT)
`docs/DOGFOODING_SCRIPT.md` B2 says *"click any action type"*. On a first
run the Policies page is empty, because section C is where the first rule
is authored. The document's own design note says it *"builds state early
and consumes it late"*; B2 consumes early. Dissolved by the fix to finding
2, but recorded because the class is the point.

### Finding 2 — the script never seeds the store; the pass cannot reach C1b (SCRIPT, BLOCKING)
Section A says **"Two terminals"** and then gives one command, and no stop
anywhere puts policies into the store. Policies enter a store only through
the service's startup loader or a library call —
`policy_loader.load_file`; the Studio reads and ratifies and never loads.
Shamik's store therefore held `policies 0 · effect_policies 0` behind a
ratified empty version, C1b had no rule to open, and three [GATE] stops
were unreachable. The script was written against a machine that had
already run the README quickstart. **It is for "a machine that has never
run this" by its own first line.**

### Finding 3 — the empty-store warning answers a question its own argv has already settled (PRODUCT, minor)
`onedoor/viewer/canvas.py:172` `STORE_WARNING`, rendered through
`screens.py:32`, asks *"Did you point --db at the service's database?"* and
explains the defaults mismatch. Shamik named `--db onedoor.db` explicitly,
exactly as the script instructs. The docstring is right that *"the Studio
cannot know which file you meant"* — but it **can** know whether `--db`
was defaulted or named, and it does not use what it knows. One condition,
at least two causes, and the message names the one that was already
excluded.

### Finding 5 — the banner label contradicts two of its three states (PRODUCT)
`onedoor/studio/shell.py:203-206`:

```python
ratified = escape(banner.ratified) if banner.ratified else NEVER_RATIFIED
f"in force {digest_html(banner.in_force)} · ratified {ratified} · "
```

The word `ratified` is emitted unconditionally. With `NEVER_RATIFIED` the
banner reads **"ratified never ratified"**; with `RATIFIED_ELSEWHERE` it
reads **"ratified not ratified through this Studio"**, which is what
Shamik saw. Only the date branch composes. The constants themselves are
correct and their docstring argues that a wrong value here would be
*"wrong in the most expensive direction: confidently, and in the field an
auditor reads first"* — and then the composition puts an affirmative verb
in front of the sentence written to deny it.

### Finding 6 — the rule editor has no door (PRODUCT, BLOCKING)
`screens.py:665` `draft_body` composes the draft page as head + origin +
diff + problems + backtest + ceremony. **No rules list, no link.** The
editor at `server.py:748` `GET /drafts/{draft_id}/edit/{action_type}` is
complete — guided pane, raw pane, `data-validate` wired for the live
checking C1b describes — and the only two `/edit/` references in the whole
Studio (`screens.py:936`, `screens.py:947`) are the form actions **on the
editor page itself**. Nothing links in. The authoring surface is reachable
only by typing a URL a stranger would have to read the source to build.
C1b, C1c and C1d are unwalkable by navigation.

### Finding 7 — an upload that refuses early yields a draft of the rules IN FORCE, silently (PRODUCT, BLOCKING)
`server.py:549` `upload_draft` stages the text, freezes the bytes, then:

```python
draft = new_draft(state, title=f"uploaded: {filename}")
if result.policies:
    save_draft(state, draft.draft_id, policies=..., effects=...)
```

`new_draft` seeds from the version in force. `staging.staged` returns
`policies=()` for **stage 1 (load)** and **stage 2 (schema)** refusals, so
`save_draft` is skipped and the draft keeps the rules already in force.
Stage 3 (per-rule) returns `policies=tuple(policies)` and is unaffected —
C2a's intended file should still work; C2b's cannot.

The route then redirects to `/drafts/{id}?uploaded=1` and
`server.py:636` `draft_detail(draft_id, backtest)` **has no `uploaded`
parameter**. The query string is ignored. Every staged refusal — stage,
message, position — is computed and discarded.

Core verified the outcome in Shamik's store: the draft titled
`uploaded: bad.yaml.txt` holds the pack's six rules with
`payments.transfer` still carrying `compensating_command:
payments.reverse`. None of the uploaded file is in it. The operator was
shown *"The validator found no problems in these rules."*

**The docstring three lines above the guard states the opposite contract:**
*"A file the loader would refuse still creates a draft. It is written to
the Studio's store with whatever parsed, and the draft's page shows the
refusals."* This is the failure mode the feature exists to prevent, and it
fails **quiet** — the worst direction available to it.

One thing works and is worth keeping: `descriptions.freeze` runs before
the guard, so the operator's actual bytes survive in the store. E10 is why
this defect is recoverable and why core could diagnose it at all.

### Finding 8 — `compensating_command` is never checked to name a registered action (PRODUCT + DOC)
`policy_loader.validate_policy` (`policy_loader.py:34`) tests
`not policy.compensating_command` — truthiness only. `decision.py:300`
does the same at runtime. **Nowhere is the named action type resolved.**
A policy naming `totally.made.up` auto-executes at tier 1 or 2 exactly as
one naming a real reversal, and the absence surfaces when the undo is
attempted, which is the worst moment available.

`docs/policy-reference.md:46` says it **"Must name another registered
action type"**, and `viewer/page.py:73` renders the reason code as *"The
action has no registered reversal"*. **The documentation asserts a check
no code performs.**

Register searched by description before filing, per R085 §1: the *class*
is registered and ruled — `PROPOSAL-20260830-ND-056` §C3 holds that
set-level defects are invisible to a per-rule loop and puts collect-all
out of scope. That ruling explains why the check is absent. **It does not
license a document claiming the check exists.** `BACKLOG.md` carries no
occurrence of `compensating_command`; `CONFORMANCE.md`'s only row marks
reversibility ✅. The doc claim is new.

## 2. What is authorized — four Studio fixes, one doc correction, one register entry

All Studio surface, docs and tests. **The engine is not touched.**

**A. Finding 6 — give the editor a door.** A rules panel in `draft_body`
listing every action type in the draft, each linking to
`/drafts/{draft_id}/edit/{action_type}`, in a defined order (sort by
action type), with the count stated. A draft with no rules renders a
sentence, never a blank — *absent is a state to render*, which is the
Studio's own law at `shell.py:72`.

**B. Finding 7 — the draft must reflect the file, and the refusals must
reach the page.** Two parts, both required:

1. When `result.policies` is empty the draft is created **empty**, not
   seeded from the version in force. A draft titled `uploaded: <file>`
   holding six rules that came from somewhere else is a false statement
   about provenance, and it is the half of this defect that is silent.
2. The staged refusals must render on the draft page: the stage, the
   message, and the position. The frozen bytes are already in
   `descriptions`, so **re-staging the frozen text when the page renders**
   is available with no schema change and keeps one source of truth —
   core's preferred shape, but the choice is yours provided the page shows
   them. Whatever you choose, `?uploaded=1` is either read or removed: **a
   query parameter no handler reads is a promise in the URL bar.**

**C. Finding 5 — the banner label.** Compose the label with the value, or
emit `ratified <date>` only in the date branch and the bare sentence
otherwise. **Do not edit the three constants**; their text is correct and
their docstring is the reasoning that makes the fix obvious.

**D. Finding 3 — the empty-store warning.** When `--db` was named
explicitly, say the store holds no policies and name how policies enter a
store (the loader, through the service or `policy_loader.load_file`).
Keep the defaults-mismatch hint for the case where it can be true. The
Studio knows which of the two it is; the message should use it.

**E. Finding 8 — the doc, and only the doc.** Correct
`docs/policy-reference.md:46-51` to state what is enforced: a non-empty
`compensating_command` is required for tiers 1 and 2, and **the named
action type is not checked to exist, at load or at decision time.**
`policy-reference.md` is a source people copy from, so it is superseded in
place, carrying the prior digest — the purpose decides the discipline, not
the seal. Then file the missing check as a new ND item in `BACKLOG.md`
**with its description written so the register can be searched by
description and not only by number**, sequenced behind the T3-for-0.7.1
queue. **Do not build the check.**

## 3. What is NOT authorized

`policy_loader.py`, `decision.py`, and every other engine file. The
compensating-command referent check. Anything on the ND-053 queue. Any
change to `validate_policy`'s raise-on-first semantics. No `git add -A`.
Nothing in `escalations/` is reopened.

## 4. The script — regenerate it, and these are the requirements

`docs/DOGFOODING_SCRIPT.md` is rewritten, not patched. Its test
(`tests/studio/test_dogfooding_script.py`) is updated to assert the new
quoted constants and the new per-section arithmetic. **The 45-minute
budget is re-derived, not retyped** — section A grows.

1. **The pass runs against a purpose-made store.** `--db pass.db
   --studio-db pass-studio.db`, created by the script's own first step, so
   a re-walk is deterministic and no accumulated drafts confuse it. F1's
   `walkthrough` command names the same `--db`. Today's pass ran against
   ambient state and the ambient state is now eleven drafts deep.
2. **Section A seeds the store**, with exact commands for PowerShell and
   POSIX: copy the shipped payments pack, load it with
   `policy_loader.load_file`, print the count and the resulting version.
   **Expect:** `6 policies loaded`, a digest, and a banner reading
   `6 policies · 2 effects`.
3. **"Two terminals" says what the second one is for**, at the moment it
   says there are two.
4. **B2 names the rule to click** — `payments.transfer` is the richest.
5. **C1b names its rule: `payouts.schedule`.** It is the pack's only
   tier-3 rule, and "open a rule" is ambiguous across six.
6. **C1c keeps `payments.refund` deliberately and gains a second beat.**
   Type it — an action that does not exist in this pack — watch the
   refusal clear; then type `payments.reverse` and watch it clear
   identically. The stop then states that the loader does not check the
   referent, citing the new ND item. An accidental demonstration becomes a
   deliberate one.
7. **C1d names `payments.transfer`**, which carries `500.00`, `5000.00`,
   `0.01`, `2000.00`. `payouts.schedule` has no decimals, so the stop as
   written could not fail.
8. **Every file the operator must create is given as an exact shell
   command that writes exact bytes** — a here-string or equivalent —
   **never as a fenced block to copy.** Today's operator saved a fenced
   block and the fence's language tag became the first line of the file,
   which refused at stage 1 and sent forty minutes sideways. *A file
   handed to an operator as prose becomes whatever their editor makes of
   it.*
9. **C3 uses `curl.exe` on Windows.** `curl` is aliased to
   `Invoke-WebRequest` in PowerShell 5.1 and `-s` throws.
10. **Every [GATE] stop states what to do when it is blocked** — record
    and continue, or stop the pass — so an operator meeting a wall knows
    which it is without asking. Today that question came upward three
    times.

## 5. The tag, and the sequence

**0.7.0 is not tagged on this pass.** A tag cut on a pass that could not
reach two of three authoring tracks would be a claim about what shipped
that the record does not support.

The sequence is: this memo's fixes → the regenerated script → **Shamik
re-walks from section A on a fresh store** → the tag. The fixes are
additive Studio surface and should be short. If the re-walk cannot
complete by **Sept 6**, the tag moves rather than the pass shrinking, and
launch week proceeds without a 0.7.0 tag rather than with an unwalked one.
Shamik can overrule that; nobody else can.

Two observations for the 0.7.1 design queue, neither of them work now.
There is **no first-run path into a store from the Studio at all** —
policies enter only through the service or a library call, which is a gap
for a product whose first screen is Policies. And the no-op ratification
Shamik performed behaved correctly: `from == to` recorded honestly,
`record_snapshot` idempotent, no phantom version. That was an unplanned
stop and it passed.

## 6. Discipline

The scrub scan runs and is **READ** before each commit. Gates re-run after
(`check-scopes` where it applies, `tsc` equivalents, the full test suite).
Split the work so the script and its test land separately from the Studio
fixes — a document and the code it describes are two claims, and a
reviewer should be able to disbelieve one without re-reading the other.

Report: the commit hashes, the scan zeros, the gate results, and a digest
for every file cited. For findings 6 and 7, report **what you saw on the
screen after the fix**, not only that the test passes — both defects are
things the tests did not catch and an operator did.

Integrity: sha256(body) = d1188ba279b6880411bb6c702749c31c14edce897e84c0e2b989ef9f2f563f81
