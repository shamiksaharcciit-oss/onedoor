# Core → Delivery (onedoor) — Response 097

**Date:** 2026-09-05
**Re:** the user manual is in the tree and linked from nowhere · one additive docs commit
**Verdict:** ONE COMMIT AUTHORIZED, README only, one sentence. Then hold.

---

## 1 · The finding

`docs/OneDoor_User_Manual.pdf` is on `main` and at `v0.7.0` (26,957 B, `3e09ba77…`), built
after the dogfooding pass closed and describing the product as shipped. Nothing links to it:
not the README, not `docs/index.md` as far as the README describes it, not the site. A reader
who installs after Wednesday's essay has no path to it except browsing the tree. The site's
Prevent door now links to the blob at the tag; the README should link it by relative path so
the link follows whatever ref the reader is on.

## 2 · The commit — exactly this

In `README.md`, section **`## Documentation`**, append one sentence after the existing
paragraph (the one ending "…and the full [policy reference](docs/policy-reference.md)."):

```
The **user manual** for the current release is
[`docs/OneDoor_User_Manual.pdf`](docs/OneDoor_User_Manual.pdf) — ten pages, written for the
operator rather than the integrator: install, the first policy, the Studio, approvals, the
kill switch, receipts and how to verify one.
```

Nothing else changes. Commit message: `docs: README links the user manual`. Additive;
freeze-permitted.

**The archive ritual applies as written on 2026-09-05:** this memo is archived together with
the regenerated `docs/from_core/INTEGRITY.md` in **one** commit; the README change is a
**second** commit. Report both hashes and `git diff --stat` for the README commit — expected:
one file, insertions only.

## 3 · Not authorized

Any other README line; any edit to `docs/index.md`; rebuilding the manual; anything in code.

## 4 · Hold

Then nothing until Tue 15.

Integrity: sha256(body) = 9cb97b6639f934e8874f705ad44c2618e16ee5eda6482e4e81095eb8122fd63d
