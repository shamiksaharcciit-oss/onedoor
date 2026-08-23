# `ND-052` / **S3** — the canvas · decomposition

**Epic:** `ND-052`, the Policy Studio. Pre-launch, demo-grade (R036).
**Ticket:** S3, third in the normative build order, on the ceremony S2 just proved.
**Baseline:** `ef0ff33`; 672 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R046 §3.

---

## 1. The three fence posts, cited rather than rediscovered

R046 §3 carried these in as settled. They are not restated here to be re-argued; they
are restated because each one **decides something concrete below**.

| Fence post | What it decides in S3 |
|---|---|
| **The canvas edits candidates and touches nothing else.** Proposer never enforcer, now with a mouse. | The only writes are to candidate storage. Ratification is **invoked** — `ratify.ratify` — never reimplemented, so the CAS, the citation check and the receipt all come along by construction rather than by the canvas remembering them. |
| **Every number the canvas shows is produced by an engine function.** The X-11-of-UIs law, extended to the Studio. | The previewed hash comes from `ratify.preview`; divergence and coverage from S1's `BacktestReceipt`; the diff from `ratify.diff`. A canvas that computes its own summary is a second implementation of a fact that has an owner. |
| **Oneview is the design system** — tokens, receipt-card anatomy, state colours are verdicts' alone. | §4's block via `tokens.css_block()`, §5's anatomy for the receipt the ceremony emits — and §3 below, which is where "state colours are verdicts' alone" turns out to have teeth. |

And one more piece of settled ground, from S2: **the candidate's identity is
`backtest.policy_digest`** — a digest over the canonical models. Not a row id, not a
name. Everything below that has to identify a candidate identifies it that way.

## 2. Finding one: Oneview's scope fence does not bind the canvas, and the spec says so

The obvious collision, resolved before it costs anyone a week. Oneview §3 is a **hard**
fence: *"Static HTML + inline CSS/JS… Read-only. No backend, no auth, no network calls
at view time."* A canvas that edits policy violates every clause of it.

It does not apply. The spec's own §1 status line says so:

> **Status:** Phase-B launch asset. Demo-grade, read-only. Product GUIs
> (onedoor ND-018/ND-020 and successors) are explicitly out of scope.

The Studio canvas is a product GUI and a successor. So §3 governs the **receipt
viewer**, and what the canvas inherits from Oneview is what R046's fence post actually
named: **§4's tokens, §5's anatomy, and §2's law**. The visual language, not the
delivery fence. Checked against the vendored bytes rather than remembered.

**The inheritance carries a hard dependency with it, and that is deliberate.**
`tokens.css_block()` **raises** rather than falling back to a bundled palette when the
spec is missing or has drifted — *a viewer that silently uses last week's palette is a
viewer that will be shipped with last week's palette*. The canvas takes that same
behaviour, X-6's shape: the design system is a hard requirement of the surface, never
an optional extra it degrades past.

## 3. Finding two: a policy diff is not a verdict, so it may not wear a verdict's colours

*"State colours are verdicts' alone"* is the fence post most likely to be violated by
reflex, because **green-for-added and red-for-removed is the single most automatic
choice a diff UI makes**. Making it would spend `--ok`/`--bad` — the one pair that
distinguishes ALLOW from DENY across three products — on *"this line is new."*

So the canvas has **two zones with different colour rights**, and the boundary is not
cosmetic:

- **The editor and the diff**: no `--ok`, no `--bad`. Additions and modifications are
  distinguished by `--seal`, weight and rule, the way §4 already permits.
- **The backtest panel**: its counts *are* verdicts — allowed, sent to approval,
  denied — and the semantic pair is exactly right there.

That distinction is a test, not a note, sitting beside `tests/viewer/test_tokens.py`'s
two existing rules — which is the pattern that made those rules stick.

## 4. Finding three: a candidate has no home yet

S1 and S2 both take a candidate as `list[Policy]`, an argument. Nothing persists one.
The canvas is the first thing that needs a candidate to **survive a page load**, and the
first that needs the *same* candidate to reach the backtest and then the ceremony
unchanged.

So S3 needs candidate storage — and one property of it matters more than its shape:
**the stored rows are an editing convenience; `policy_digest` is the authority.** A
receipt cites a candidate by digest, and the digest is computed from the models at the
moment it is used. If a stored row and a digest ever disagree, the digest wins, because
the digest is what a backtest receipt and a ratification receipt already carry.

Two consequences follow without needing a ruling:

- **A draft is not evidence, so its table is not append-only.** Editing is the whole
  point; an immutable draft table would seal every keystroke. What must not be revisable
  is the *receipt*, and `ratifications` and `backtest_receipts` already hold that line.
- **A candidate seeds from the active set as a copy.** The natural first move is "load
  what is live and change one rule", and a copy keeps fence post one intact — the canvas
  reads the active policies and writes only to the draft.

## 5. Finding four: the engine's validator raises at the first problem; an editor needs all of them

`policy_loader.validate_policy` is fail-closed and raises `ValueError` on the first
thing it finds. That is right for boot and wrong for a canvas: an editor that dies on an
invalid draft is not an editor.

The canvas must **not** grow a second validator — that is fence post two exactly. So S3
adds a **collecting wrapper over the same function**: call `validate_policy` per rule,
catch, collect. The engine keeps raising; the Studio gets a list.

**And the wrapper must state its limit rather than imply completeness**: it reports at
most **one problem per rule per pass**, because the underlying validator stops at the
first — and set-level problems (an effect floor that only bites once two rules are read
together, a `compensating_command` naming an action the candidate also removes) are
invisible to a per-rule loop. A wrapper that presented its list as "all problems" would
be the overclaim this programme exists to make impossible; it reports *problems found*,
and says so in those words.

## 6. Work order

- **T1** — candidate storage and the collecting validator. Migration `0019` (shape
  pending Q2). The validator half is unblocked today.
- **T2** — the canvas surface: how it is served and reached (pending **Q1**).
- **T3** — the editor and the live diff against the active set, with the staleness rule
  (pending **Q3**).
- **T4** — the numbers panel: previewed hash, divergence, coverage — each from its
  engine function, each labelled with the state it was produced from.
- **T5** — the ratify action: invokes `ratify.ratify`, renders its refusals **verbatim**
  — the lost race and both citation reasons — rather than paraphrasing them into one
  "could not ratify".
- **T6** — the Oneview skin and the colour-rights test of §3. Unblocked today.

## 7. The questions this decomposition surfaces

**1. What is the canvas's surface?** Finding one removes the *design*-spec objection but
not the product question, and this one freezes T2 through T5. Three shapes:

  - **(a) routes on the existing `onedoor.service` app**, behind the admin key;
  - **(b) a separate local-only Studio server**, bound to loopback, `python -m
    onedoor.studio`;
  - **(c) a static page plus a CLI apply step** — edit in the browser, export a
    candidate, ratify from the command line.

  Delivery leans **(b)**, and the reason is a security one rather than a taste one:
  `onedoor.service` is the **PDP** — the machine-to-machine endpoint agents call for
  decisions. Putting an operator GUI that *changes the rules* on the same app means one
  leaked admin key both answers decisions and rewrites the policy those decisions are
  made under. Separating the surfaces means the PDP's credential never grants
  policy-editing. **(c)** is the most faithful to Oneview's habits and delivery does not
  recommend it: a static page cannot run `ratify.preview`, so it could show no
  engine-produced number at all, which collides head-on with fence post two.

**2. Where does a candidate live?** Delivery proposes a **mutable** `policy_candidates`
table in the same store, migration `0019`, with the digest as the authority (§4).
Against it: the store's culture is append-only, and this would be the first mutable
table the Studio adds to it — `backtest_receipts` and `ratifications` are both sealed.
For it: a draft is not a claim about the world, drafts and receipts are already
different things in this design, and the alternative — a separate Studio store — puts a
candidate somewhere the ratification ceremony cannot reach it without a second
connection. **Delivery is not confident enough to decide this one alone**, because "the
Studio writes mutable rows into the enforcer's database" is the kind of sentence that
needs to be true on purpose.

**3. When the active policy moves under an open canvas, does the diff re-base?** This is
S2's compare-and-swap arriving one layer earlier. If the canvas re-diffs live, the
picture silently becomes a diff of something the operator never chose to read — which is
exactly the stale-read the CAS refuses at write time, except here it happens *before*
anyone clicks, so the CAS would pass. Delivery leans **pin and surface**: the canvas
diffs against the version it was opened on, and a change to the active set raises a
visible "the rules moved beneath this draft" state that the operator resolves
deliberately. The same reasoning covers the previewed hash, which costs a scratch
database and so cannot be recomputed per keystroke: **a preview is labelled with the
state it was produced from, and a stale one is visibly stale rather than quietly
wrong.**

T1's validator and T6 are unblocked. T1's storage waits on Q2; T2 through T5 wait on
Q1, which decides whether there is a server at all.
