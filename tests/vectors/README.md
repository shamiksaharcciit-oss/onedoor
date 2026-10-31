# Test vectors for onetrace

Stable, documented data files, generated once by `onedoor`'s own real code against
a fixed clock and a fixed (public, non-secret) Ed25519 keypair, then committed as
the vectors themselves. `test_vectors.py` in this directory re-verifies every file
against the same functions it was generated from, so a change to those functions
that moves a value is caught here before it reaches anyone vendoring these files.

A consumer that vendors `onedoor.decision_digest` and `onedoor.decision_ref`'s
checker (both stdlib-only, by design) does not need to run `onedoor` at all to use
these files — they are plain JSON, read and compared against directly.

**The permit vector's keypair is a test key, not a credential.** `permits.json`'s
issuer public key exists only to make that one vector's signature reproducible
and checkable; its matching private key was used once, by the generator, and was
never committed anywhere. It has no use outside this directory: it is not in any
default trust file this package ships, and nothing outside `tests/vectors/`
references it. Do not configure a real deployment's `permit_issuer_private_key`
or any issuer trust table with it.

**`confirmation_vectors_3.json`'s keys are RFC 8032 §7.1's own published test
keys** (TEST 1, 2, 3, 1024) — public by design, not secrets at all, and still
with no use outside this directory: not in any default trust file this
package ships, and not packaged in the wheel.

## Files

- **`action_digests.json`** — action objects (bound-permit profile §4.3) and their
  action digest (`sha-256=:...:`, `onedoor.permit.action.action_digest`), including
  a decimal-string amount, a nested object, and Unicode text.
- **`decision_refs.json`** — one export (as `onedoor.export.write_export` would
  write it) and five `onedoor-decision-ref/1` objects, each engineered to give
  exactly one of `onedoor.decision_ref.check`'s five outcomes against that export:
  `matches`, `digest_mismatch`, `not_in_export`, `malformed_ref`, and
  `export_damaged` (a property of the file, not any one row — see the note on
  that case; it is demonstrated in `test_vectors.py`, not representable as a row).
- **`permits.json`** — one bound permit (compact JWS), the issuer's public key as a
  JWK, and three cases against that same permit: one whose paired action object
  matches what was signed (`verifies`), one paired with a changed amount
  (`action_digest_mismatch` — a different action object, not a different
  signature), and the same permit checked at a time past its own `exp` claim
  (`expired`). Verified with `onedoor.permit.jws.verify` for the signature,
  `onedoor.permit.action.action_digest` for the action binding, and the `exp`
  claim (Unix seconds) against a given check time for lifetime — the narrower set
  profile §8.1 defines for this, not the full recipient replay/audience check
  `onedoor.permit.recipient.verify` does.
- **`preimage_v6.json`** — `decision_digest` stability across the preimage `/6`
  bump (migrations `0030`, `0031`): a row written before those migrations existed
  keeps the exact same digest once they run, and the two new columns are included
  in the digest whenever a `resume_request_mismatch` denial actually sets them.
  Each row is exactly what `export_rows` would emit.
- **`confirmation_vectors_3.json`** (format `confirmation-vectors/3-draft`) —
  the recipient confirmation (bound-permit profile §10, V22): one shared
  permit and signed request, and 29 cases (`C01`-`C29`), each naming its own
  steps (name, recorded outcome, confirmation token) and the exact verdict and
  detail of the format note's own five verifier rows (request, permit,
  key/`typ`, single use, outcome). `gen_confirmation_vectors_3.py` is the
  generator -- not shipped code, and not kept in this folder either: it is
  in the format note's own pack, outside this repository.
  `check_confirmation_rows_3.py` is a second, independent
  implementation of those five rows, written from the format note's text
  alone — it imports nothing from `onedoor` or `onetrace` — the same
  "a second implementation that agrees with itself has proved nothing"
  discipline `docs/row-preimage.md`/`test_row_preimage.py` already follow for
  the audit chain. `test_confirmation_vectors.py` checks three things
  independently: the file reproduces byte for byte from this repository's own
  `onedoor.permit` code; every one of `onedoor.permit.confirmation.check`'s
  own four rows (it does not implement single use directly — see
  `find_reused_permits`) and `confirmation.build`'s "once step N passed"
  branches read every vector as expected; and `check_confirmation_rows_3.py`
  agrees with the file's own stated `expect` for all 29 vectors' five rows.
  See `docs/confirmation.md`. Superseded `confirmation_vectors_1.json`
  (C01-C21) and `confirmation_vectors_0.json` (draft 0, C01-C12) entirely;
  neither earlier file is kept alongside it.

## Regenerating

These files are generated, not hand-written, but the generator is a one-off
script, not shipped code — if the underlying functions change, write a new
generator against the new code and replace these files with its output; the
regenerated vectors must still pass `test_vectors.py`.
