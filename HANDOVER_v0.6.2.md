# Handover — publishing `onedoor 0.6.2`

**For Shamik.** The patch release carrying the two findings from your walk through
`0.6.1`. The commands needing your credentials are §4 and §5. **Shell: PowerShell**,
single-line, no continuations.

**Tag:** `v0.6.2` → commit `95a6150d943b33aaa3edb12f3826e1ed910758f6`, pushed.

---

## 0. Read this first — do not rebuild

**The digests in §3 are of the exact files in `dist/` right now. Upload those. Do not run
`python -m build` again before uploading.**

The build is **not byte-reproducible** — measured during `0.6.0`: two builds of the same
tree differ, the wheel keeping its size and changing its hash. A digest taken after
publication would prove nothing about what was verified. *A digest answers exactly one
question, and this one answers "are these the bytes we verified", never "would building
again produce them."*

## 1. What this fixes — F-G and F-H

| | Finding | Status |
|---|---|---|
| **F-G** | the Studio's empty state was a dead end | **Fixed** |
| **F-H** | the two default database filenames disagree, silently | **Fixed** |

**F-G.** The Studio index with no drafts emitted **0 forms, 0 buttons, 0 inputs, 0
links** — its entire body read *"onedoor policy studio no drafts"*. It now offers a
create-draft form and the equivalent `curl` one-liner, on the empty state and beside a
populated list alike. *A state with no next move is a wall, not a state.*

The form needs **no JavaScript and no new dependency**: the route reads the
`application/x-www-form-urlencoded` body with the standard library, because
`request.form()` would pull in `python-multipart` even for urlencoded bodies. Your browser
gets a **303 to the draft it created**; the JSON API, which passes `title` as a query
parameter, still receives JSON byte-identically. The caller's content type decides, so
nothing that worked before changed.

**F-H.** The decision service defaults to `onedoor-service.db`, the Studio's `--db` to
`onedoor.db`. Accept both defaults and they point at **different stores** — the Studio
comes up, works, and shows you an empty world. It now says so when the enforcer store it
opened has never held a policy, naming both defaults and the flag that is probably wrong,
and the README's quickstart spells the same filename in both commands. *A wrong default
that cannot be noticed is a defect twice.*

**Also fixed, found while building F-G:** a browser form POST returned `422` before
reaching the handler. `from __future__ import annotations` makes every annotation a
string, and FastAPI resolves route annotations against the **module's** globals — not the
closure the routes are built in. `Request`, imported inside that function, was invisible
at resolution time, so `request: Request` was read as a missing *query parameter*. Now at
module scope behind an import guard; the X-6 property is unchanged.

**Not in this release:** F-B (decimal strings in `params`). It changes a verdict from
`denied` to `permitted`, and core ruled that direction never rides a hotfix into launch
week. `ND-054` is specced and held; `README.md`'s *Known limitations* carries the gap.

## 2. What was verified, and how

Gates through their own runner — `python -m scripts.gate --all`, ruff 0.16.4 and mypy on
CPython 3.12.10:

```
PASS  lint     All checks passed!
PASS  format   157 files already formatted
PASS  types    Success: no issues found in 67 source files
PASS  tests    893 passed, 9 skipped
```

The P0 tests were **written first and shown failing**: 8 of 11 red against the shipped
code before the fix existed. A test that has never failed has never been shown to look.

Then, against a **clean venv installing the built wheel**, over a real socket — not a test
client:

```
version: 0.6.2
form / title input / button present : True True True
curl one-liner present              : True
empty-store warning                 : True   (names both defaults)
browser POST (urlencoded)           : 303 -> /draft/bca6895609034af6b79d68a2aa43d991
title honoured in the listing       : True
external origins referenced         : none
```

`twine check`: both artifacts **PASSED**. Wheel contains **18 migrations** and **2
templates** — the check that `0.3.0` taught us to run.

## 3. The artifacts — digests taken before upload

| file | bytes | sha256 |
|---|---|---|
| `onedoor-0.6.2-py3-none-any.whl` | 250,759 | `6093133a4d48007a2593b4cc15919e5bdcc8a92a3a7944d802a8f28998e2942f` |
| `onedoor-0.6.2.tar.gz` | 292,226 | `5651731fc20b22e33f39be8e046cb01b73690dde7d64461428eebd8b2e4c216b` |

## 4. Upload to PyPI — your credentials

```powershell
python -m twine upload dist/onedoor-0.6.2-py3-none-any.whl dist/onedoor-0.6.2.tar.gz
```

## 5. The GitHub release — same motion as the tag (R011)

```powershell
gh release create v0.6.2 dist/onedoor-0.6.2-py3-none-any.whl dist/onedoor-0.6.2.tar.gz --title "onedoor 0.6.2" --notes-file RELEASE_NOTES_v0.6.2.md
```

## 6. Then tell me, and I verify

Send me the PyPI and release URLs. I check the published digests against §3 **via the
index API, not your upload transcript** — the transcript is a claim about what was sent,
the index is the artifact that arrived — and I dereference the annotated tag before
comparing commits.

---

## 7. What happens next

`ND-055`'s **V1–V8 are held for `0.7.0`, after Sept 12** — core's R056 ruled the S4/S6
seal migration rides V1's shell work so the token change lands exactly once. Nothing
breaking lands between now and launch. This release is additive and documentation-shaped
by design.
