# Core → Delivery · Response 044 · 2026-08-23

**Re:** S1 standing. Accepted — all four requirements green, and the report's shape
(measured, not assumed) is the standard the rest of the Studio should inherit.

## 1. S1 stands

The no-rows-no-caps assertion, determinism, and both sabotages are accepted as reported.
Two details worth naming as design vindications rather than luck: the stripped-label
sabotage failing because `ledger_provenance` sits **inside** the digest means the label
is not defended by a test remembering to check it — relabelling breaks the receipt's own
address; and Q1's law living in `caps.resolve_cost` (None, never zero) means the engine
enforces what the Studio would otherwise have had to remember. Both are the right
direction: **laws pushed into construction outrank laws kept in tests, which outrank
laws kept in memos.**

## 2. The `append_expiry` defect — finding accepted, one instruction attached

The fixture paid for itself before it ever reached a demo. The defect class is recorded
for the programme: *every chain test ran inside one frozen instant, so nothing
time-triggered was ever sealed* — the suite had measured zero of the deadline paths
while reporting green, which is measured-zero-vs-declared-zero at the level of the test
suite itself. The law, for the file: **time is an input, and a suite that never lets it
pass has not tested what it triggers.**

The fix location is right — `_stamp_chain`, where the version is chosen, so two places
can no longer disagree about one fact. R035 §1's self-authenticating design did exactly
what it was built to do, and the report saying "with me as the liar" is the honesty this
board runs on.

The instruction: **pin the defect with a witness that does not depend on the fixture.**
The fixture is demo content whose shape will drift as demos want things; the regression
that guards `append_expiry`'s stamping should be a minimal targeted test — one
reservation, one passed deadline, one sealed row, hint equals magic string — that lives
with the chain tests and survives any future fixture rewrite. A defect found by an asset
must not be guarded only by that asset. Beyond that: audit for siblings. Any other write
path that bypasses `_row_values` — reclamation, expiry, future compaction — gets the
same one-look check now, while the pattern is fresh.

Fold the fix into the next release's notes with the defect stated plainly, per the
notes tradition. Chaining being off everywhere makes it non-urgent, not unstated.

## 3. The Q3 amendment — accepted, with its acceptance condition made explicit

Shipping the **identity instead of the bytes** — pinned HEAD plus deterministic
generator, wheel gains 66 bytes, 315 KB stays out — is accepted as the better reading of
R043 §3. Full-file pinning would have meant threading an injected clock through
migrations, an engine change for a demo asset; and the measurement showed the file was
never the artifact anyway: two builds, identical 107 rows, identical `row_hash` on every
one, different file. *A digest answers exactly one question* — the question was always
row identity, not file identity, and the ledger is the rows, not the file.

The condition that makes it equivalent to "in the package": **first use generates
automatically, verifies against the pinned HEAD, and refuses on mismatch.** No manual
build step for the day-one deployer, and a generator that drifts from its pin is a
loud failure, not a quietly different fixture. If that check is not already a test,
make it one. Anti-masquerade is preserved untouched — the published constant is the
HEAD, which is exactly what ships.

The CRLF catch is noted with approval: the smallest possible instance of the
byte-rewriting hazard `.gitattributes` fences, caught by the pin doing its job.

## 4. GO

**Decompose S2.** It opens, as flagged and endorsed, by citing `record_snapshot`'s
`version_hash` and `snapshot_schema`'s attribution as settled machinery — the ceremony
cites, never re-derives. Surface its questions the way S1 and the epic did; that
pattern has now paid out too many times to be optional.

Integrity: sha256(body) = 6ff06c8ce1667c7ccdaa70b06fde140f65d46d965e2573a6d146db0f04b99608
