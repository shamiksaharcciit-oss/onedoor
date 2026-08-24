# onedoor 0.5.0

Notes drawn **verbatim** from [CHANGELOG.md](CHANGELOG.md)'s `0.5.0` section (R011:
release notes are a slice of the changelog, never a rewrite of it). Conformance status
with every gap named lives in [CONFORMANCE.md](CONFORMANCE.md); the ticket-by-ticket
plan is in [BACKLOG.md](BACKLOG.md).

---

**Additive. Nothing existing changes meaning.** No wire-observable change: no new reason
codes, no changed verdict shapes, no altered two-phase exchange. A `-00` enforcement
point is unaffected. Seven forward-only migrations (`0012`–`0018`) apply on first run.

**This release is the evidence pillar.** `ND-001` chains audit rows, `ND-015` signs
them, `ND-017` anchors them into an RFC 6962 Merkle tree, `ND-010` lets a permit outlive
the process that issued it, `ND-009` resumes through an approval, and `ND-051` renders
the result as a receipt you can read. Every one of them is **opt-in and off by default**:
an installation that changes nothing behaves exactly as it did under `0.4.1`.

The line the whole epic exists to hold: **onedoor never vouches for itself.** A
signature this store can check against its own keyring is `self_consistent`, never
`verified`; `verified` requires something the store does not hold. The viewer renders
that distinction rather than flattening it, and shows the failure state instead of the
value whenever verification is not sound.

**The Policy Studio ships behind the `[studio]` extra, and it is incomplete on purpose.**
Included: the **backtest engine**, the **ratification ceremony**, and the **canvas**. Not
included: the coverage map, the finance pack, and the proposer. It is a proposer and
never an enforcer — nothing in it writes to the decision ledger, the canvas server binds
loopback only, and drafts live in a separate `studio.db` because the enforcer's database
contains no row the Studio can edit.

**Upgrading:** run the engine once to apply the migrations. Nothing else. To turn on the
evidence features, see `docs/row-preimage.md` and `chain.enable`; signing additionally
needs `onedoor[signed]`.

### Added — `ND-052` / S3: the policy canvas

An editor for candidate policies that shows the hash they would become, the rules they
change, and what they would have done to the ledger — then invokes S2's ceremony.

- **A separate, loopback-bound process.** `python -m onedoor.studio` is not part of
  `onedoor.service`, and that is a security boundary rather than a packaging choice:
  the service is the PDP, and **one leaked credential must not both answer decisions and
  rewrite the rules those decisions are made under.** The server **refuses to bind
  anything but loopback** — a literal loopback address or `localhost`, nothing else,
  refused before a socket exists. A hostname is refused *without being resolved*,
  because a boundary that depends on what DNS said a moment ago is a lookup, not a
  boundary. There is no flag that turns the refusal off; a flag that turned it off would
  be the config drift it exists to catch.
- **Drafts live in the Studio's own `studio.db`.** The enforcer's database contains no
  row the Studio can edit. Mutability already lives in the main store *where the enforcer
  owns the mutation*; what it has never held is a row a second process edits. Losing
  `studio.db` loses drafts and nothing else — receipts are evidence and stay sealed where
  evidence lives.
- **Pin and surface.** A draft is pinned to the version it was opened against and never
  silently re-bases: a live re-base is a stale read arriving before the click, where
  ratification's compare-and-swap cannot catch it. A moved active set **names both
  hashes** — a warning that names no versions is a mood, not a fact — and every computed
  number goes stale *together* and recomputes together, because the panels are one object
  rather than three fields.
- **Validation collects instead of raising, without becoming a second validator.** The
  canvas wraps `policy_loader.validate_policy` and reports its messages verbatim. It says
  **"problems found"**, never *all problems*, and renders that notice even when the list
  is empty: the engine's validator stops at the first failure in each rule, and defects
  that only appear when rules are read together are invisible to a per-rule check.
- **Refusals travel verbatim.** A lost race and the two citation failures reach the
  canvas with their own words and their own named reasons, never flattened into "could
  not ratify" — they are distinct facts with distinct remedies.
- **Oneview, minus the fence that does not apply.** The canvas takes §4's tokens, §5's
  anatomy and §2's law; §3's static/read-only delivery fence governs the receipt viewer,
  as the spec's own status line says. State colours stay verdicts' alone: the diff zone
  separates additions by seal, weight and rule, and the semantic pair appears only in the
  backtest panel, whose counts *are* verdicts. Held by a test in both directions.

New optional extra `onedoor[studio]`. No AADP wire-observable behaviour changes, and the
engine gains no dependency: the Studio's FastAPI requirement is hard at the point of use
and absent everywhere else.

### Fixed — two imports the CI environment did not install

`uvicorn` and `langchain-core` are imported by the package and were missing from the
`[dev]` extra, which is all CI installs. `uvicorn` arrived with the Studio server and
turned CI red on both jobs; `langchain-core` was already there and had been passing only
because `langchain` happens to pull it in — a gate that would have gone red on a morning
nobody touched the code, the moment an upstream restructured its requirements.

Both are now declared. The mypy override that would also have turned CI green was
rejected: silencing `ignore_missing_imports` makes the gate pass by making it check
less, and the one call site the dependency exists for is exactly the site that then goes
unchecked.

A test now closes the class locally: `tests/test_packaging.py` reads the package's own
ASTs and asserts every third-party module it imports resolves to a distribution `[dev]
`installs, with exceptions carrying written reasons.

### Added — `ND-052` / S2: the ratification ceremony

Diff a candidate against what is in force, **see the hash it would become**, ratify, and
get a receipt. This is the act that turns a *candidate* — which has only a digest over
models — into a *version* recorded in `policy_versions`.

- **The previewed hash is the produced hash.** The number shown is not computed
  alongside `record_snapshot`; it is produced *by* it, in a scratch store that is thrown
  away. The scratch store holds the candidate **merged over the active set**, because
  the snapshot renders the whole policy table and seeding it with only the changed rules
  yields the hash of a two-rule deployment — a different number wearing the right label.
  A sabotage test does exactly that and watches the equality fail.
- **A lost race refuses; it never silently writes.** Ratification is a compare-and-swap
  against the `version_hash` the diff was read from. A UI has a gap between reading and
  clicking, and an operator must not sign something other than what they read. It
  refuses loudly and does not re-diff on the operator's behalf.
- **A cited backtest is checked at the ceremony.** The digest must resolve in this store
  *and* its `policy_digest` must equal the candidate's — otherwise refusal, under two
  **different** named reasons, because a citation that resolves to nothing and one that
  resolves to a test of a different candidate are different facts. Ratifying without a
  backtest stays allowed, and **the absence is rendered in every view** rather than left
  as a null nobody sees. Where a backtest *is* cited, its `ledger_provenance` is
  surfaced by dereferencing: a fixture-informed ratification is legitimate and must be
  visible as one.
- **`ratified_by_session`, not `ratified_by`.** onedoor has no authenticated per-caller
  identity, so the field holds a *declared* session, and every rendering says
  "declared, not authenticated". A field's name is part of its honesty. An
  authenticated principal will be `onedoor/ratification/2`.
- **The receipt exports as two files** — itself and the snapshot it names — and verifies
  from those alone: the receipt matches its own digest, and the snapshot hashes to the
  version it ratified. No database, no deployment.

Migration `0017` adds the append-only `ratifications` table.

### Changed — the kill switch does not block ratification, and the lift now says why

The switch wins over every action under every policy, so nothing ratified can move while
it holds: **the moment of risk is the lift, not the ratification.** Blocking policy
edits mid-incident would punish the operator tightening rules while stopping no attacker
who already had ratification access.

So the state is recorded rather than enforced — `kill_switch_engaged` is a hashed field
on every ratification receipt — and the *release* path is where a change becomes loud.
Migration `0018` records the policy version in force when the switch is engaged, and
releasing it reports any change since: *"the rules changed while the door was shut, from
X to Y."* Surfaced through both the admin endpoint (`policy_change_while_engaged`) and
the MCP proxy; **the lift is not blocked either.** This product makes states visible; it
does not take the wheel.

The report has **four** states and none collapses into another: `changed`, `unchanged`,
`undeterminable` (an episode with no recorded version) and `no_episode` (a store
upgraded while the switch was already held). Only `unchanged` says the rules held still,
and it says it because two hashes were compared.

`killswitch.set_engaged` now returns that report on release and `None` on engage; the
admin endpoint's response gains a `policy_change_while_engaged` field. No AADP
wire-observable behaviour changes.

**Known limitation, stated rather than implied away:** a ratification cannot *retire* a
rule. `upsert` has no delete and the candidate merges over the active set, so an omitted
action type stays exactly as it was — and the receipt's `changes` therefore reports
`added` and `modified` and has no `removed` field at all, rather than carrying one that
can never be non-empty.

### Fixed — reclamation rows were sealed under one preimage version and claimed another

`append_expiry` writes the `reservation_expired` row that records budget going back when
a permit's deadline passes unreported. It does not go through `_row_values`, where
`preimage_version` was stamped — so **every reclamation row was sealed under
`onedoor/row-preimage/2` while its hint claimed `/1`**, and a verifier reading the hint
recomputed the row under the wrong field order. Every one failed verification.

**No deployment is affected**: chaining is opt-in and off by default, so no production
store has sealed a row at all.

It survived the whole crypto epic because **every chain test runs inside one frozen
instant, where no reservation deadline ever passes**. The Studio's fixture ledger — three
simulated days of traffic — was the first thing that reclaimed anything, and all 23 of
its reclamation rows failed at once. The law that came out of it: **time is an input, and
a suite that never lets it pass has not tested what it triggers.**

The hint is self-authenticating by design, so the defect surfaced as a loud failure
rather than a silently accepted row — the mechanism working exactly as specified, with
this project as the liar. The stamp now lives in `_stamp_chain`, where the sealing
version is chosen, so two places can no longer disagree about one fact. A targeted
regression (one reservation, one passed deadline, one sealed row) guards it independently
of the fixture, and a structural test asserts that **every** audit write path stamps the
chain — so a future compaction or archival writer cannot inherit the same gap.

One behaviour changed alongside it: an **unchained** row now carries no version hint at
all. A hint on a row that was never sealed is a claim about a sealing that did not
happen.

### Added — `ND-017`: content-addressed receipts and Merkle anchoring

**The crypto epic's last ticket.** Each chained row now carries four content-addressed
digests — `e_digest`, `i_digest`, `t_digest`, `v_digest`, in columns dark since `0007` —
and ranges of rows are anchored under RFC 6962 roots a deployer publishes outside the
store.

`docs/receipt-digests.md` is the normative definition, with a second implementation
built from it and six golden vectors. The four were read from the vendored artifact's
own scheme rather than invented, and **confirmed by arithmetic**: the shipped manifests
carry `t_digest = 4f53cda1…b945`, which is SHA-256 of canonical `[]` — so `T` really is
a *declared closure* and not a bag of facts. Every digest is over canonical JSON, so **no
concatenation appears and the `len8` dialect is not reached** — said plainly rather than
decorated with an unused framing.

Two amendments from R040, both where delivery's flags pointed. **`T` does not carry the
policy hash**: `E` already seals it as an input identity, and the same hash in two
preimages is X-14 *inside the seal itself*. **`I` does not carry the anchor cadence**:
cadence schedules anchoring, not deciding, and inside `I` an ops-schedule tweak would
have re-identified the deciding instrument for every row after it. It lives on the anchor
object, where a change is visible in the stream it governs.

**`anchor_ref` can never be written**, and the design is better for it. It is a column on
`actions_audit`; anchoring necessarily happens after a row is sealed; the no-update
trigger forbids `UPDATE` — verified against a live store, not assumed. So the anchor
points at a *range of rows* and membership is resolved by lookup. A back-reference would
have been a second answer to a question the range already answers, needing a writable
column on the one table whose value is that it cannot be written.

**X-8, and the reason stated where it is enforced:** the chain is verified before a root
is computed, and a fault anywhere refuses the seal — an anchor over a broken chain would
publish a root that certifies damage, permanently and in public.

**onedoor never vouches for itself: at the key layer and the anchor layer alike,
`verified` requires something the store does not hold.** A proof that checks against a
root the store carries is `self_consistent`; `verified` needs the published root. And
because anchoring is periodic, the newest rows read **`absent`** — a viewer that showed
them red would train an operator to ignore red.

The acceptance is an **environment**, not an assertion: the third-party verifier runs in
a subprocess whose working directory holds exactly the anchor and the receipt. If it
ever needed the database, that test would fail rather than look fine.

### Added — `ND-015`: signed decision receipts (Ed25519)

Each chained row is signed over its `row_hash`, with the signature, the derived
`key_id` and `alg` landing in columns that have existed dark since `0007`. **No hashed
column, no preimage version** — a signature attests the row hash and cannot precede it,
which is why those three were classified `EXCLUDED` before this ticket was written.

**A receipt system must not be its own witness.** A signature checked against a public
key found in the **same store** as the row it signs proves internal consistency, not
authenticity: an attacker with write access adds their own key, re-signs what they
altered, and the store agrees with itself perfectly. The append-only triggers do not
close it — a keyring must accept `INSERT`s or rotation is impossible — and the chain
does not either, because a keyring row is not an audit row.

So signature checks have **five** outcomes, and the middle one is the point:

| | |
|---|---|
| `verified` | checks against a `key_id` **the caller supplied from outside the store** |
| `self_consistent` | matches this store's own keyring — real information, and not verification |
| `unverifiable` | the key is unknown here; the signature may be perfectly good |
| `failed` | the bytes do not verify |
| `absent` | no signature: signing was not in operation |

`self_consistent` exists because collapsing it into `unverifiable` would throw away a
check that genuinely passed, and calling it `verified` would be the store witnessing
itself. The viewer renders it in its own class — **never green** — with the sentence
*"supply a trusted key to verify"* beside it. An adversarial test demonstrates the whole
argument: an attacker registers their own key, re-signs a row, the store reports
`self_consistent`, and an external anchor still refuses it.

**Custody.** The private key is deployer-supplied and never enters the repo, the
database or a receipt — asserted by a test that greps every stored value for key
material. `key_id` is **derived**, a fingerprint of the public key, never assigned: a
chosen label can drift from what it names and a digest cannot. **Rotation is
append-only** (migration `0014`, with the same no-update/no-delete triggers as
`actions_audit`): a retired key stays, because the receipts it signed must verify
forever.

**X-6 at enable time, not install time.** `cryptography` is a `[signed]` extra — a
library-only user who never signs should not carry it. The failure that matters is a
deployment that believes it signs and does not, and a hard install dependency does
nothing about that, because belief comes from config. So **signing configured plus
library missing means the process refuses to start**, asserted as a stated invariant.

`alg` records **`ed25519` (RFC 8032) and not the library**: Ed25519's output is
deterministic, so a library version in per-row evidence would assert a dependence that
does not exist. The library and its pinned version are recorded once at the deployment
layer — semantics in the receipt, process provenance in the register.

### Added — `ND-009`: PEP-driven resumption via `approval_ref`

An enforcement point can present a reference to an approval a human already granted.
Resumption is a **new** decide with a **new** `request_id` carrying the ref, and the
binding is **action-equivalence**, not `request_id` — a PEP presenting it on a different
request is doing the required thing.

**Every failure mode behaves identically and differs only in evidence.** Expired,
consumed, forged, wrong-action, not-yet-approved: all of them resolve to *not
authorised*, the action re-evaluates on its own merits, and a Tier-3 action simply
proposes again. A bad ref never grants — and never errors, because an error path would
tell a prober whether the ref existed. The forensic difference lives in
`approval_ref_status`, the seven-value evidence field, and **not one reason code was
added**.

**Action-equivalence is identity up to spelling** (R035 §3): same `action_type`, and
params equal under the canonical rendering. Key order and `250.00` versus `250` are
spelling; `250` versus `900` is not. The human saw params, so an approval for €250
cannot be spent on €900 — which effect-set equality alone would have allowed, since
both share a `money.egress` label.

**Single-use survives a race.** Consumption is the *first* write and its `rowcount` is
the gate, inside the `BEGIN IMMEDIATE` the decision already holds. Two simultaneous
resumptions yield exactly one execution, and the loser proposes: **a lost race never
denies and never errors; it just does not grant.**

**The kill switch still wins** after a valid ref, asserted as an invariant rather than
left to emerge from check ordering — and the evidence records *both* facts, `honored`
alongside the `kill_switch` denial, rather than blaming the approval.

`principal_mismatch` is **reserved and never emitted**, held by a test exactly as
`sender_mismatch` is. onedoor has no authenticated per-caller identity — `session_id`
arrives in the same untrusted body as the ref — and scoping to it would be a control
that does not control anything. The value ships so the vocabulary is complete in one
increment; it starts being emitted when `ND-004`/`ND-005` provide an identity.

**Found while building it:** `Decimal("250")` serialises to the JSON integer `250`, and
`json.loads(..., parse_float=Decimal)` returns an **`int`** — `parse_float` never sees
an integer. So the stored side of an approval carried `int` where the presented side
carried `Decimal`, and equivalence reported `action_mismatch` for **every whole
amount**. Safe (no grant) but wrong. Numbers now render through `canon_decimal`, and
are **tagged** so a numeric `250` cannot collide with the string `"250"` — the vendored
artifact's rule 4 names that trap, and here it would be permissive in the worst way:
the bounds gate that refuses a string amount never runs once a ref has granted.

### Changed — the row preimage is now versioned: `onedoor/row-preimage/2`

`approval_ref_status` is **hashed**, because it records *why* an approval did or did not
authorise an action — flipping `expired` to `honored` is exactly the edit a chain exists
to catch. Hashing a new column is a new preimage version, so `/2`.

Migration `0013` also adds **`preimage_version`**, a per-row hint **excluded** from the
hash and self-authenticating: the authority is the magic string inside the preimage, so
a row whose hint disagrees with how it was sealed fails verification under the version
it names. A lying hint produces detection, not confusion.

**This ends the one-shot window.** `prev_hash` links are unaffected by a version change
— each row hashes the previous row's `row_hash`, whatever produced it — so a ledger
whose rows transition `/2 → /3` re-derives end to end, and future columns get future
versions **on live chains**. Before the hint, a new hashed column was possible only
while chaining was off everywhere and impossible for anyone who had switched it on,
because the table forbids `UPDATE` and sealed rows can never be re-hashed. `/2` was the
last bump that needed that window, and the boundary case is verified by a test.

`sig`/`key_id`/`alg` stay excluded (a signature attests the row hash and cannot precede
it) and `anchor_ref` stays excluded (X-8 anchors after re-verification, and an edited
anchor fails the Merkle proof — the right detector for it). `ND-050` was deliberately
**not** pre-folded: guessing its row shape to save a bump would be designing a ticket in
a hurry inside another one.

### Added — `ND-010`: a permit outlives the process that issued it

`service/app.py` kept pending intents in a dict and its own docstring promised `0.4`
would rebuild them from the `exec_intent` row instead. Until now a restart between
decide and report stranded every in-flight permit: the reservation stayed held, the
deadline ran, and the reclaimer eventually voided budget for an action that may well
have happened. `state.pending` is now a **query against the ledger**, and `/v1/report`
looks the intent up rather than popping memory.

Reconstructed permits are **the same durable rows** — no new evidence identity, no
budget re-reservation — asserted by counting audit rows and cap counters across a
simulated restart rather than by trusting the code path.

**A rebuilt permit is its own type, and that is the design.** `rationale`, `cost_eur`
and `session_id` are stored nowhere in `actions_audit`, so reconstructing an
`ActionRequest` would mean passing `cost_eur=Decimal(0)` — **a default that looks like
a fact**, which any later reader would take at face value. `RebuiltIntent` has no such
field, so the mistake is unavailable rather than avoided, and it carries provenance
references to the rows it derives from.

**A wrong label on a receipt, caught before it shipped.** `report_result` hands the
request to `audit.append`, which calls `frozen_params`: that returns `params_raw`
verbatim, or **re-serialises when `params_raw` is None** — and only a live ingress sets
`params_raw`. A post-restart result row would therefore have stamped
`params_provenance = "serialized"` on bytes that arrived `received`. Not a crash and
not a test failure: a quiet falsehood in the evidence, written at the moment the system
is least observed. A rebuilt permit now carries the intent row's frozen bytes and its
provenance, exactly as `append_expiry` has always done for reclamation rows.

**A rebuilt row's `created_at` is its own write time, never backdated.** The ledger
records when it *learned* a thing; a rebuilt row carrying the original's timestamp
would be the ledger testifying to a moment it did not witness. `RebuiltIntent` names
the other one `requested_at` and has no `created_at` at all, so a caller cannot reach
for the wrong one.

**Four outcomes at recovery time**, and the middle two are why it is a type rather than
an `Optional`: `rebuilt`; `absent` (never permitted, or already reported — the ordinary
answer); `unverifiable` (the evidence disagrees with itself — `cap_reservations` has no
foreign key to `actions_audit`, so a held reservation naming a missing intent is
reachable); `failed` (stored and unreadable). `/v1/report` maps them to distinct HTTP
statuses: an absent intent is a client asking about nothing pending (404), while an
unverifiable one is the store disagreeing with itself and is nobody's client error
(500). Collapsing them would report a damaged ledger as a bad request.

### Added — `ND-001`: hash-chained audit entries

Each audit row now hashes its own contents plus its predecessor's hash, so a deletion
or an in-place edit breaks the chain and a walker localises the break to the row that
moved. **Off until switched on** — `chain.enable()` is a deliberate, once-only,
recorded act, and an upgrade alone changes nothing.

**The preimage is the ticket, and it is frozen.** `docs/row-preimage.md` defines the
exact bytes `row_hash` covers, written so an implementer with no access to the source
can reproduce every digest from that text alone. `tests/guardrail/test_row_preimage.py`
holds **a second implementation built from the document rather than from the code** —
an implementation that agrees with itself has proved nothing — plus the four golden
vectors R031 §1.3 named: the shift collision, absent-versus-empty, a value containing
the framing's own header bytes, and a one-byte perturbation.

- **Absent is a type tag, never a zero-length string.** Every field enters as an
  `ABSENT` tag with no payload, or `PRESENT` + an 8-byte big-endian length + the bytes.
  NULL and `""` differ in their **first byte**. `budget_json` NULL means *no budget was
  owed* and `""` would mean *a budget was produced and it was empty*; R015 makes those
  different facts, and this is where an adversary would look for the collapse.
- **The vendored artifact carries no length-prefix dialect**, checked rather than
  assumed — no `struct`, no `to_bytes`, no packing anywhere in it. So the encoding is
  written down in full as R031 required, built on the one byte-level discipline the
  artifact does ratify: RFC 6962's domain-separation tags.
- **A column is hashed or deliberately excluded, never neither.** A test asserts every
  column of `actions_audit` appears in the field order or in the exclusion table with
  its reason, so a future migration fails until someone classifies the new column. A
  column that silently fell outside the hash would be a field an attacker could edit
  without breaking the chain, and it would look complete in review.

**Group commit is kept, not refused** (N2). The chain is stitched inside `flush`
before the `executemany`. Refusing it would have made a performance feature and an
integrity feature mutually exclusive, and every deployer wanting both would quietly
disable the one that is harder to notice missing. **Measured consequence, stated
because the decomposition first claimed otherwise:** buffering defers result rows, so
the ledger's *row order* differs between the two paths and their chains differ with
it. That is what group commit is. The invariant that holds — and the one the decision
needs — is that **the preimage does not depend on which path wrote the row**.

**Verification reports four outcomes and never averages them.** A log with an
unchained prefix and an intact chain after genesis is not "verified" and not "failed";
it is both, stated per region. Rows before genesis are `absent` — they cannot be
hashed retroactively because the table forbids `UPDATE`, and that is history rather
than damage. A chain that is partly written is `unverifiable`. A row whose contents no
longer hash to its record is `failed`, localised to itself rather than poisoning every
row after it.

**The viewer did not change.** `ND-051` rendered the chain block's absent state naming
this ticket; `ND-001` fills the columns, `_check_chain` flips from `absent` to
`verified`, and the page renders real digests with **not one line of `page.py`
edited** — asserted as a test. That is what "one verification, and the viewer does not
own it" was for.

**Upgrading:** migration `0012` adds a `UNIQUE` index on `seq` so the database refuses
a duplicate chain ordinal rather than leaving it to the walker. Index only — the chain
*columns* have existed since `0007`. Existing rows are untouched and stay unchained.

### Added — `ND-051`: the receipt viewer

`python -m onedoor.viewer --store <path> --out <page.html>` reads an audit store and
emits **one static, read-only HTML page**: the decision receipt as the hero object,
with the checks that back it, and the tail of verdicts in the order the ledger took
them. No backend, no network at view time, no dashboard — the design spec's scope
fence is enforced by a test rather than by intention.

**One verification, and the viewer does not own it.** The checks live in
`onedoor.guardrail.receipt` and the page renders their output. The rule is structural
and tested: the renderer imports no hashing module, reaches into the engine only for
the verifier, and cannot construct a status from a string. Two implementations of "is
this sound?" eventually disagree, and the one the user sees would be the wrong one.

**Four outcomes in a user interface** — `verified`, `absent`, `unverifiable`, `failed`
— and the distinction is the product rather than a technicality:

- **`absent`** is *not yet in operation*. Hash-chained entries (`ND-001`) have not run,
  so `row_hash`, `prev_hash` and `seq` are NULL, and the chain block **says so, naming
  the ticket**. The reference mockup shows a digest there. Rendering one from a NULL
  column would have been the easiest thing in the world to do and would have been
  fabrication. The wording is deliberate: *not yet in operation*, never *not yet
  produced*, so absent-by-schedule is never readable as broken.
- **`unverifiable`** is *produced and then lost* — a policy snapshot row that is gone, a
  chain that is half written. It renders **as loudly as an outright failure**, because a
  check that could not run is not a check that passed.
- If verification is not sound, the page shows the **failure state and none of the
  receipt's values**. Not the values behind a warning: a reader copies the number and
  leaves the caveat behind.

Both mandatory tests are **sabotage-verified in CI**, and the assertion is exact rather
than "something failed": render-as-if-verified fails the failure-state property **and
no other**; a fabricated digest fails the X-11 property **and no other**. A third
sabotage was added unasked, because it is the likelier real mistake — nobody fabricates
a digest on purpose, but somebody will format `10` as `10.00` to make a column line up,
and under E8 those are the same value and different evidence.

Design tokens are vendored **byte-identical** from the spec's own code fence and
digest-pinned; a revised spec raises rather than silently rendering last week's
palette. Every colour on the page is a token, checked; no verdict rule may use the
brand accent.

`--demo-store` builds a **labelled** sample store by running the real engine, never by
writing audit rows by hand, and **the label travels in the store rather than on the
command line** — a flag is forgotten, a row in the artifact is not.
