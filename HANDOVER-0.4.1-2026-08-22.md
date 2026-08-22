# Handover — onedoor `0.4.1` · for Shamik's credentials

**Staged by:** delivery · **Date:** 2026-08-22 · **GO:** Response 027 §3
**Commit:** `61fb46a` (`release: onedoor 0.4.1`) on `main`
**Nothing below has been published.** PyPI upload and the GitHub release both need
your credentials; the commands are exact and the artifacts are already verified.

---

## 1. What this release is

`ND-040` — URL-valued parameters are matched as URLs rather than as strings, plus the
declared opaque-host class that catches redirectors, plus the corrected disclosure.

**Additive.** New opt-in policy vocabulary (`param_effects[].url`) and two
forward-only migrations. Every rule already deployed matches exactly what it matched
under `0.4.0` — asserted by a compatibility corpus, not merely intended. No new reason
codes, no changed verdict shapes, no signature changes; a `-00` enforcement point is
unaffected.

---

## 2. Artifacts — verified, do not rebuild

Built from `61fb46a` with a clean `dist/`. **Upload these exact files.** Python wheels
embed timestamps and are not byte-reproducible, so rebuilding produces different bytes
than the ones verified below and these digests would no longer describe what you
uploaded.

The one commit that follows `61fb46a` adds only this handover and
`scripts/release_smoke.py`. Neither is packaged — checked, not assumed: the wheel
contains no `scripts/`, and the sdist ships only `onedoor/`, `LICENSE`,
`pyproject.toml`, `setup.cfg`, `MANIFEST.in`, `README.md`, `CHANGELOG.md` and
`CONFORMANCE.md`. So the artifacts' *content* is `61fb46a`'s either way; the digests
are of the bytes that were verified.

```
ee8054cc1dbc90bdb29123c3b2291c50e62bc2f53404bbedff6b13749431b687  dist/onedoor-0.4.1-py3-none-any.whl   103527 bytes
61cd143c7a64d5a9e5b4ac4adcab421ad1c8658c2e691692e33fdb8710ebe3be  dist/onedoor-0.4.1.tar.gz             121881 bytes
```

Confirm before uploading, if you want to (PowerShell):

```powershell
Get-FileHash dist\onedoor-0.4.1-py3-none-any.whl -Algorithm SHA256
Get-FileHash dist\onedoor-0.4.1.tar.gz -Algorithm SHA256
```

### What was actually run against these bytes

Not "should work" — each line below is a command that ran and the output it produced.

| Check | Command | Result |
|---|---|---|
| Package metadata | `twine check dist/*` | `PASSED` (both artifacts) |
| Migrations in the wheel | inspected the zip | **11**, matching 11 on disk, ending `0011_opaque_evidence.sql` |
| Clean-venv install, **wheel** | fresh venv → `pip install dist/onedoor-0.4.1-py3-none-any.whl` → `scripts/release_smoke.py` | `OK` |
| Clean-venv install, **sdist** | fresh venv → `pip install dist/onedoor-0.4.1.tar.gz` → `scripts/release_smoke.py` | `OK` |

The migration and clean-install checks exist because **`0.3.0` shipped a wheel with no
migrations and failed on its first query**. `scripts/release_smoke.py` goes further
than `import onedoor`: it runs `Database.init()`, confirms all eleven migrations
applied and the three new evidence columns exist, then makes four real decisions on
`0.4.1`'s new surface —

```
  https://weather.example.com/today          -> permitted
  https://bank%2Eexample%2Ecom/transfer      -> proposed/effect_floor
  https://t.co/x9k2                          -> proposed/effect_floor
  https://bank%2Fevil.test/x                 -> denied/malformed
```

— which is the whole release working from a cold install: an innocent untouched, a
percent-encoded host caught, a declared redirector escalated, an unreadable target
denied.

### Gates on `61fb46a`

Each run with the workflow's own command, and read from its output rather than its
exit code:

```
ruff check .            -> All checks passed!
ruff format --check .   -> 90 files already formatted
mypy onedoor            -> Success: no issues found in 37 source files
pytest -q               -> 392 passed, 8 skipped
```

**Before you run anything below, check CI is green on `61fb46a`** — both `py3.12` and
`py3.13`. The local run is not the gate; read the run's own `conclusion`, not the exit
code of whatever prints it.

---

## 3. Commands for you to run, in order

### 3a. PyPI

```powershell
cd C:\Users\polo2\Downloads\onedoor
.venv\Scripts\twine.exe upload dist\onedoor-0.4.1-py3-none-any.whl dist\onedoor-0.4.1.tar.gz
```

Both files named explicitly rather than `dist/*`, so a stale artifact left in the
directory cannot be uploaded by accident.

### 3b. Tag and GitHub release — one motion (R011)

```powershell
git tag -a v0.4.1 -m "onedoor 0.4.1 - ND-040: URL-typed parameter matching"
git push origin v0.4.1
gh release create v0.4.1 --title "onedoor 0.4.1" --notes-file RELEASE_NOTES_v0.4.1.md dist\onedoor-0.4.1-py3-none-any.whl dist\onedoor-0.4.1.tar.gz
```

`RELEASE_NOTES_v0.4.1.md` is a **verbatim slice** of `CHANGELOG.md`'s `0.4.1` section,
cut by script and asserted to be a substring of it — not a rewrite. Notes written
twice say two things.

**Do not backfill a release onto an older tag.** A retroactive release carries a date
that misstates when the artifact was published, and this project does not manufacture
provenance.

### 3c. Confirm

```powershell
pip download onedoor==0.4.1 --no-deps -d C:\Temp\verify041
gh release view v0.4.1
```

---

## 4. After it is published

Tell me, and I will write the `0.4.1` ping to core. It carries: `ND-040` closed with
the corrected mechanism sentence, the opaque-host invariant and the defect found
while asserting it, `ND-050` newly ticketed, and the `§implstatus` question of whether
any draft text needs revising — **paper and draft claims are core's, and I do not edit
them.**

---

## 5. Honest scope of this handover

- **Nothing has been published.** No upload, no tag, no release. Every command above
  is for you to run.
- **The digests are of the artifacts in `dist/` right now.** If `dist/` is cleaned or
  rebuilt before you upload, they no longer apply and the verification above no longer
  describes what ships — ask me to re-stage rather than rebuilding yourself.
- **CI on `61fb46a` was not confirmed at the time this file was written.** Check it
  before 3a.
- The four decisions in §2 were run against **these exact artifact bytes**, in fresh
  virtual environments, not against the working tree.
