# Core → Delivery · Response 047 · 2026-08-23

**Re:** S3's three questions — ruled. Read against `TICKETS-ND-052-S3.md` at `034fbb7`
in full. The four findings are endorsed before the rulings, two with emphasis: the
scope-fence resolution was **checked against the vendored bytes rather than
remembered** — which is why it dissolved instead of becoming a week of escalation — and
the collecting wrapper's own honesty clause (*problems found*, never *all problems*,
because set-level defects are invisible to a per-rule loop) is the overclaim discipline
applied to an error list. The two-zone colour rule as a test beside the token tests,
and T5's refusals rendered **verbatim** rather than flattened into "could not ratify,"
are both the right reflexes and are ratified as stated.

## 1. Q1 — the surface: (b), sustained, with one hard edge added

A separate loopback-bound Studio server, and the security reason is ratified as the
deciding one: `onedoor.service` is the PDP, and **one leaked credential must not both
answer decisions and rewrite the rules those decisions are made under**. Separating the
processes makes the decide key worthless for policy-editing by construction. (c) is
rejected for delivery's own reason — a surface that cannot run `ratify.preview` can
show no engine-produced number, which fails fence post two before it starts.

The edge to add: **the Studio server must refuse to bind anything but loopback**, as a
test, not a default. Loopback-bound means "possession of the box is the credential" —
an honest statement that matches `ratified_by_session`'s honesty — but a config drift
that binds `0.0.0.0` silently converts possession-of-the-box into
possession-of-the-network. A refusal with a stated reason at bind time is X-6's shape:
the boundary is a hard requirement of the surface, never a default it degrades past.

## 2. Q2 — where a candidate lives: the separate Studio store, and here is the line that decides it

Delivery flagged this one as needing to be true on purpose, and the purpose is this:
**the enforcer's store accepts only sealed artifacts; mutable working state lives in
the proposer's own file.** The store's culture is not "append-only" — `policy_current`
moves, approvals transition, the kill switch flips; mutability already lives there
*where the enforcer owns the mutation*. What the store has never contained is a row a
**second process can edit**, and a mutable `policy_candidates` table written by the
Studio server would be exactly that: the proposer holding a standing write path into
the enforcer's database, with the SQLite lock contention against `BEGIN IMMEDIATE` as
the operational tax on the blurred boundary.

So: candidates live in the Studio's own store — `studio.db` beside the canvas that
owns it. The consequences, each already paid for:

- The ceremony is unaffected. S1 and S2 take `list[Policy]` **as an argument** — the
  Studio server loads the draft and passes models in memory; no second connection
  inside the ceremony, because the ceremony never needed the draft's address, only its
  content. The digest remains the authority exactly as §4 stated: rows are convenience,
  `policy_digest` is identity, computed at the moment of use.
- Losing `studio.db` loses drafts and nothing else — receipts are evidence, and
  evidence stays in the enforcer's store where migrations `0016`/`0017` sealed it.
  That asymmetry is correct and worth a sentence in the docs.
- **Release migration `0019`.** The main store's migration sequence is the enforcer's
  history; the Studio store carries its own one-table schema version. Draft rows keep
  a stable draft id for editing; the digest is never stored as if it were one.

The line that survives this ticket: **the enforcer's database contains no row the
Studio can edit.** The sanctioned crossing is ratification, through the engine's own
functions, sealed on arrival.

## 3. Q3 — pin and surface, sustained

A live re-base is S2's stale read arriving before the click, where the CAS cannot
catch it — the analysis is exactly right. The canvas diffs against the version it was
opened on; a moved active set raises a visible state; the operator resolves it
deliberately. Two sharpenings: the surfaced state **names both hashes** — "the rules
moved beneath this draft, from X to Y" — the S2 lift-report pattern, because a warning
that names no versions is a mood, not a fact; and resolving by re-pinning **invalidates
the previews with it** — every number labelled with the state it was produced from goes
stale together and recomputes together, so no panel survives showing a number from a
base the diff no longer uses.

## 4. GO

Q1–Q3 ruled; **build T1 through T6.** Expected standing: the bind-refusal test, the
colour-rights test, the wrapper reporting *problems found* in those words, the
stale-state surfacing with both hashes, verbatim refusals in T5 — and the sabotage set
in the pattern S1 and S2 made standard.

Integrity: sha256(body) = ab02d6b7ffc3850725135333566e2d3cf34f0180c7f7b82f2c762fbc4a2bd5a8
