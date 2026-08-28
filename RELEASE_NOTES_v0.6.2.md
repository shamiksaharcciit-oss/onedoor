# onedoor 0.6.2

Notes drawn **verbatim** from [CHANGELOG.md](CHANGELOG.md)'s `0.6.2` section (R011:
release notes are a slice of the changelog, never a rewrite of it).

---

### Fixed — `ND-055` P0: the Studio's empty state, and the silent database trap

Both found by Shamik working through `0.6.1` by hand. Additive and documentation-shaped;
no engine change, no schema change, no wire change.

**F-G — the empty state was a dead end.** The Studio index with no drafts emitted **0
forms, 0 buttons, 0 inputs, 0 links**; its whole body read *"onedoor policy studio no
drafts"*. It now offers a create-draft form and the equivalent `curl` one-liner, on the
empty state and beside a populated list alike. *A state with no next move is a wall, not a
state.*

The form is plain HTML and needs **no JavaScript**: the route reads the
`application/x-www-form-urlencoded` body with the standard library, because
`request.form()` would require `python-multipart` even for urlencoded bodies and a
dependency for one text field is one the `[studio]` extra does not need. A browser
submission gets a **303 to the draft it created**; the JSON API, which passes `title` as a
query parameter, still receives JSON — the caller's content type decides, so nothing
existing changed.

**F-H — the silent database trap.** The decision service defaults to
`onedoor-service.db` and the Studio's `--db` to `onedoor.db`, so accepting both defaults
points them at **different stores**: the Studio comes up, works, and shows an empty world.
The Studio now says so when the enforcer store it opened has never held a policy, naming
both defaults and the flag that is probably wrong, and the README's quickstart spells the
same filename in both commands. *A wrong default that cannot be noticed is a defect twice.*

### Fixed — a browser form POST returned 422 before it ever reached the handler

Found while building F-G. `from __future__ import annotations` makes every annotation a
string, and FastAPI resolves route annotations against the **module's** globals — not the
closure `create_app` builds them in. `Request`, imported only inside that function, was
invisible at resolution time, so FastAPI read `request: Request` as an unresolvable
**query parameter**. The name now lives at module scope behind an import guard, and the
X-6 property is unchanged: importing the module still works without FastAPI, and
`create_app` still refuses with a remedy.
