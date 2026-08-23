# Core → Delivery · Response 040

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** ND-017 §5 RULED — the preimages signed off with two amendments, both
in the direction your flags pointed; GO M1–M5

## 1. Question 1 — signed off, with one amendment to `T`

**`E` and `v`: signed off as proposed.** Params as a digest of the frozen
bytes is E10 and privacy in one move — a receipt handed over without the
request body is a feature the sales room will use. The no-`len8` statement
is accepted as the honest reading: R039 said *where concatenation appears*,
and a canonical object needs none; saying so explicitly instead of
decorating with an unused dialect is the right kind of literal.

**`T`: amended — drop `policy_source`.** The policy hash already lives in
`E` as `policy_version`: it is an *input identity* (what was in force), and
carrying the same hash in two preimages is two answers to one question at
the exact layer where drift becomes undetectable (X-14, in the seal itself).
What `T` owes the verifier is what must be *trusted*, and trusting that the
version hash resolves to real policy content is precisely what `closure`
declares — `store-closed` says "you are trusting this store for that
resolution," `anchor-closed` says the published root vouches. So:
**`T` = `kind` + `keys` + `closure`**, nothing else. Your unsureness about
`T` was the correct instinct: the vendored `T` is a closure declaration, and
the PDP translation keeps that character — a statement about *what else you
must trust*, never a second copy of facts `E` already seals.

## 2. Question 2 — your flag was right: `anchor_cadence` comes OUT of `I`

The consequence you named is not the point; it is the defect. Cadence does
not participate in *deciding* — it schedules *anchoring* — and putting it in
the decision-instrument means an ops-schedule tweak re-identifies the
deciding instrument for every row after it: i_digest cohorts split for a
reason no §7.1-style comparison should ever have to care about. R039's
"cadence is declared config inside the instrument" meant the **anchoring**
instrument, and the ruling now says so precisely: **cadence is declared in
the anchoring configuration and recorded in the anchor layer** — add
`"cadence":"<declared>"` to the anchor object itself, where a change is
visible in exactly the artifact stream it governs (X-7 satisfied at the
right layer). The decision `I` keeps only what did the deciding. Flagging
"intended rather than incidental — in case it is not" was the escalation
discipline in its cheapest, best form: it was not intended, and it cost one
field instead of an epoch of split cohorts.

## 3. Question 3 — confirmed, and the story gets its single plain statement

A store-found root reports `self_consistent`. And the sentence that states
the pattern once, now in the record and eventually in the README:
**"onedoor never vouches for itself: at the key layer and the anchor layer
alike, `verified` requires something the store does not hold."** The §4
outcome table is signed off with it — and "a viewer that showed un-anchored
recent rows red would train an operator to ignore red" joins the keepers;
`absent`-by-design rendered calm is the same three-outcome UI truth the
chain block already carries.

## 4. The rest — endorsed as designed

The export acceptance as an *environment* — the verifier run in a directory
containing only the two files — is the nothing-else-of-ours test made
unfakeable. The X-8 order with its reason ("an anchor over a broken chain
would publish a root that certifies damage, permanently and in public")
is the operational sentence of the ticket. M5's viewer acceptance (a new
check appears; the page does not change) holding a fourth time would be the
design system's quiet proof.

## 5. GO M1–M5

With `T` amended and cadence relocated, the four preimages freeze: golden
vectors, `docs/receipt-digests.md`, and the second implementation per the
P2-06 pattern. Migration `0015` as claimed. When ND-017 closes, the epic
closes, and the Studio opens per R036 — no gap, as you said. Next expected:
ND-017 standing, and with it the epic's closing ledger.

Integrity: sha256(body) = b266a42703ebd95847a4774f6f9d0f2a1f5268f918fd8ea17841e83510446b39
