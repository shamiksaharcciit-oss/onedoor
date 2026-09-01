# onedoor 0.7.0 — **DRAFT B: T3 SLIPS**

> **This is a draft for core's review and Shamik's scope approval. It is not published, and
> delivery does not publish it.**
>
> **Variant B of two.** This variant is correct **if T3's published-misses benchmark has
> not cleared by Sept 5**. Use **Draft A** if it has.
>
> **T3 is absent from this document, not described as coming.** That is deliberate and it
> is the capability rule doing its job: a release note that promises a feature is
> aspiration presented as capability, and this project does not ship those. When T3
> arrives it will be announced by the release that contains it.
>
> Notes drawn from [CHANGELOG.md](../../CHANGELOG.md)'s `0.7.0` section (R011: release
> notes are a slice of the changelog, never a rewrite of it).

---

## What this release is

**The Policy Studio, finished.** `0.6.2` shipped two fixes to a Studio that was one screen
and a canvas. `0.7.0` is the whole room: eight screens that read the policy set, the
ledger, the live state and the receipts — and two ways to write a policy.

### Why the number is `0.7.0` and not `0.6.3`

Because a version number describes content. This release carries the entire Ledger Room
arc — eight screens built over `ND-055` — plus two new authoring paths. Calling that a
patch would understate it to the only audience version numbers exist for. The number
follows what is in the release; it was not chosen to fit a date.

**This release removes nothing.** No endpoint retired, no field dropped, no behaviour
changed for anything that was already working. Every addition below is additive, and the
engine, the wire protocol and the enforcer's schema are untouched.

---

## Writing a policy, two ways

Every one of them produces a **draft**. A draft changes nothing. The only path from a
draft to the rules an agent is actually governed by is the ratification ceremony, which is
a page a person reads and confirms.

### In the editor

A guided form and the raw rule, two panes over one parsed object, so they cannot disagree
with each other. **Validation now runs as you type**: the text goes to the server, the
engine's own loader looks at it, and the answer comes back rendered. Nothing is parsed in
the browser — which is why the panes and the validator cannot drift apart, and why turning
scripting off leaves you exactly the editor `0.6.2` had.

### From a file

Upload YAML on the Drafts page. The file is checked by the loader's own four stages, in
the loader's own order, and the draft shows what would be refused at boot, at which stage,
and where in the file.

**A file the loader would refuse still becomes a draft.** You get the reasons, not your
file handed back.

Before this release, the Studio could only ever reach the *last* of those four checks,
because the editor handed it rules that had already survived the first three. The point of
the track is a single sentence: **nothing the loader would refuse at boot should first be
discovered at boot.**

### Over the API

`POST /api/v1/drafts` and the routes beside it: read, list, add or update one rule, ask
what the loader thinks, and submit for ratification. The schema is at
`/api/v1/openapi.json`.

> The v1 API adds no approval route — ratification belongs to the human ceremony. One
> legacy route (POST /draft/{id}/ratify), predating actor identity, still serves; it
> records its approver as declared, never authenticated, and is retired with the key_id
> work.

It now says so in its own response.

`submit` records that a human has been asked. It moves no version pointer and writes no
receipt.

---

## Two lists, and why they are two

The Studio separates what the loader will refuse at boot from how a rule that loads
perfectly well will behave once a request arrives:

- **The loader would refuse this** — what fails at startup.
- **Once in force, these rules will…** — decision-time behaviour, each line naming the
  reason code the engine will actually record.

They are never merged, and the distinction is not cosmetic. A euro cap with no `cost_param`
**loads**; the engine denies at decision time with `cost_unknown`. Showing that as a boot
refusal would tell you the engine refuses something it accepts — and an operator who learns
that stops believing the list that was right.

Neither list claims completeness. The refusal list carries the notice that the engine's
validator stops at the first failure in each rule; the behaviour list says only what it
knows how to predict.

---

## The rest of the room

**Policies** — every rule in the version in force, read from that version's snapshot, with
what each rule does in plain English beside the rule itself. A version whose snapshot
cannot be read says so, rather than rendering as an empty policy set.

**History** — the execution ledger, chain-numbered, with every filter that shaped the view
visible in the view.

**Live state** — the kill switch and the budgets. The switch's state is shown and no
button is drawn, with the reason stated: this process may not write to the enforcer's
store, and a control that renders as operable and is not would be worse than none.

**Re-evaluate under any version** — take a decision the ledger recorded and replay it under
a different policy version. The engine decides; nothing is re-executed; both versions are
named in the same breath; and a version whose rules cannot be retrieved renders as *not
retrievable* rather than replaying as an empty policy set.

**Verify** — a page built for a stranger. It gives you two files and a command that reads
them, opens no database, and tells you `verified`, `failed`, or `unreadable` — three
outcomes, because telling you your receipt is bad when what is bad is your download would
be the worst error the page could make.

**The ceremony** — ratification is a page before it is an action. Reading it ratifies
nothing. It states what will be in force, what changes, and what this does not undo — and
it does not call the change irreversible, because that would be false: there is no
un-ratify, and the way back is forward.

---

## Installing

```bash
pip install --upgrade "onedoor[studio]"
python -m onedoor.studio --db onedoor.db --studio-db studio.db
```

Then open `http://127.0.0.1:8787`. The Studio binds loopback only and refuses anything
else before a socket exists.

**`--db` must name the same file your decision service uses.** The service defaults to
`onedoor-service.db` and the Studio's `--db` to `onedoor.db`, so accepting both defaults
points them at different stores.

Existing Studio stores are upgraded in place on first open. Existing policy databases are
untouched — this release adds no enforcer migration.

---

## What has not changed, and what this does not claim

- **No engine change, no wire change, no enforcer schema change.** The decision path is
  byte-for-byte the one `0.6.2` shipped.
- **Nothing is removed.** No deprecation takes effect in this release; the one deprecated
  route still serves and says so.
- **The Studio still edits no live rule.** Everything it writes goes to its own store; the
  enforcer's database contains no row it can edit, ratification excepted and sealed.
- **Decimal strings in numeric bounds remain a known limitation**, unchanged and noted in
  the editor at the fields it affects. The fix is specced and lands after this release.
- **The ledger records no caller identity.** The Studio says so on the screen where that
  matters rather than answering identity questions with provenance facts. Actor identity
  is specced and follows.

Integrity: sha256(body) = c405e827fa4cf6ef1dbe1ca03df1980961403e4d146b8021f9bc81a9aafb1bda
