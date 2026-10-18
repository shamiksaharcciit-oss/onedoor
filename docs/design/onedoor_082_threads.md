# Design note: multi-threaded and multi-process callers

Covers ruling item 4 (OD1) for 0.8.2. Note only — no code, now or in this release. The
limitation stays stated, not fixed, in 0.8.2.

## What the existing limitation means, precisely

CHANGELOG.md's known-limitations entry: "A multi-threaded or multi-process deployment that
bypasses the documented single-writer model can see a window between checking a condition and
acting on it... The documented deployment (one process, one SQLite writer behind an internal
lock) does not have this window; a deployer who runs multiple writers against the same store
without that serialization can."

Tracing why the documented deployment is safe: `onedoor/store/db.py`'s `tx()` (lines 52-65)
issues `BEGIN IMMEDIATE` at the top of every decision, before any read
(`onedoor/guardrail/decision.py:222`, `with tx(conn):` wraps the whole body, including the cap
read in `check_and_reserve`, `caps.py:294-337`). That is correct and sufficient **as long as
every caller sharing one database file is actually serialized at the SQLite level** — which
the documented deployment guarantees a second way, redundantly: `onedoor/service/app.py:193-203`
and `onedoor/integrations/langchain_middleware.py:167` each open exactly one connection and wrap
every call in a `threading.Lock()`, so two requests inside one process never even attempt
concurrent `BEGIN IMMEDIATE`s.

The actual exposure is not in that path. `onedoor/store/db.py:45` sets `PRAGMA
journal_mode=WAL`. WAL's writer-exclusivity (and `BEGIN IMMEDIATE`'s lock) is coordinated
through shared-memory primitives (the `-wal`/`-shm` sidecar files) that are well documented
(upstream SQLite) to behave unreliably or not at all over most network filesystems. A
single-process deployment never exercises that path — its serialization is the Python lock,
which needs no cross-process primitive at all. A deployer who instead runs **multiple
processes** against one store — the case the limitation actually names — depends on exactly
the primitive that is least trustworthy outside local disk. `busy_timeout=5000` (db.py:47)
turns a lock collision between two same-host processes into a 5-second wait and then a raised
`sqlite3.OperationalError`, not a silent race; the silent race is specifically the
network-filesystem case, where the lock coordination itself can fail to exclude at all.

## Two directions, not a decision

**A lock.** An application-level mutual-exclusion primitive that does not depend on SQLite's
own file-lock coordination — e.g. a dedicated lock acquired through a mechanism that works
regardless of filesystem (an external coordinator, or a primitive the deployment's own
infrastructure already trusts). Every writer, in every process, acquires it before its own
`BEGIN IMMEDIATE`. Cost: one more thing to deploy and get wrong; it only moves which
primitive the correctness argument rests on, and a deployment that cannot trust its
filesystem's locking is not obviously one that can be trusted to run a second coordination
service correctly either.

**A transactional check.** Leave exclusion to SQLite entirely, and instead make every mutating
statement self-verifying: structure the write as an `UPDATE ... WHERE <the condition, read
in the same statement>` and inspect `cursor.rowcount` rather than trusting a separate prior
read.
This is not a new pattern here — `onedoor/guardrail/approvals.py`'s compare-and-set consume
(module docstring: "State transitions use compare-and-set so the TTL-expiry race is closed")
already does exactly this for approval consumption, and the same shape is named again in
`onedoor/guardrail/approval_ref.py:23-24` and `mandate.py:178` ("the race decide itself" /
"a race decide itself rather than double-grant"). Extending that shape to `caps.py`'s
counter reservation — read and write in one statement, check the row count, refuse rather than
assume on a miss — would make correctness independent of whether the surrounding `BEGIN
IMMEDIATE` actually excluded every other writer. Cost: every mutating statement in the cap and
approval paths needs re-shaping to this form, and a few (multi-row reservation across several
effect-label counters at once, `_reserve_all`) do not reduce to one `UPDATE` as cleanly as a
single counter does.

Neither is implemented or chosen here. A transactional check is the more self-contained
change (no new deployed primitive, extends an existing in-house pattern) but does not fully
remove the network-filesystem risk for the very first read in a request, since the engine
still opens its `BEGIN IMMEDIATE` before anything else runs; a lock removes it precisely where
it is needed but adds an operational dependency. Which one to build, and whether to build
either before someone actually deploys onedoor against a store on shared network storage, is
a call for whoever reviews this note, not this note.

## What stays true in 0.8.2

No code changes. The CHANGELOG's existing known-limitations entry stands unchanged; the
documented, supported deployment (one process, one connection, one internal lock, local disk)
is unaffected by anything above and remains race-free exactly as it is today.
