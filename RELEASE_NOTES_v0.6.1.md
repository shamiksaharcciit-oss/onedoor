# onedoor 0.6.1

Notes drawn **verbatim** from [CHANGELOG.md](CHANGELOG.md)'s `0.6.1` section (R011:
release notes are a slice of the changelog, never a rewrite of it).

---

**A patch release from the first operator validation against shipped bytes.** Shamik
installed `0.6.0` from PyPI on a clean machine and worked through the whole surface as a
first-time user; five items came back. Four are fixed here. The fifth changes a verdict, so
it is escalated rather than taken locally.

Nothing here is breaking. No wire-observable change, no migrations.

### Fixed — the Studio server returned Internal Server Error on every page

`GET /` failed deterministically with
`sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same
thread`. The Studio's stores are opened once at startup, and every route is a sync `def`,
which FastAPI runs in a **threadpool** — a different thread per request.

**Every library-level test passed while the served surface was broken**, which is the
lesson worth keeping: *a gate is a command and the world it runs in*, and the route
function and the route under uvicorn's threadpool are different worlds. **A served surface
is now tested through the server** — `tests/studio/test_server_served.py` reaches the app
with `TestClient` the way a browser does, including eight sequential requests, because a
single request can pass by thread luck.

The fix is the pair `onedoor.service` has always used: both connections opened
`check_same_thread=False` **and** every route serialised on a lock. Those go together —
the flag alone would trade a loud error for a quiet race — so `StudioState` owns both and
neither is optional.

### Fixed — `onedoor.__version__` did not exist

A stranger's first sanity check failed. It now reads from the installed distribution, so it
cannot drift from `pyproject.toml`: a version derived is the only version that cannot rot.

### Fixed — the Studio app self-described as version `0.4.x`

A literal that was already wrong when `0.5.0` shipped and had no way of ever becoming
right — a name outrunning its artifact, in the one field whose job is to say which artifact
this is. Now derived from `onedoor.__version__`.

### Added — a four-command quickstart in the README, for someone who has only PyPI

Install, copy the shipped pack, set keys, run — with the three outputs that tell a reader
it worked. The previous quickstart began `pip install -e ".[dev]"`, which assumes a clone;
the repository workflow is now a subsection beneath it. Every command was run from a clean
venv against published bytes before being written down.

### Known limitation, newly named — decimal strings in `params`

`{"amount_eur": 120.00}` works; `{"amount_eur": "120.00"}` is refused by a `numeric` bound
as *must be numeric* — while `cost_eur` accepts the string form and the cap path already
reads a decimal string as money. Measuring it found something sharper than the report:
**adding a `numeric` bound changes which wire types an action accepts**, because
`caps.resolve_cost` accepts `str` and `bounds` does not.

The failing direction is closed — a denial, never a permit — and the fix **changes a
verdict**, which makes it core's call rather than a maintainer's. Escalated as
`escalations/ESCALATION-20260827-006.md`; named in *Known limitations* meanwhile, so an
integrator meets it in documentation rather than in a refusal.

### Fixed — the formatter could reach outside the source tree

`ruff check . --fix` from the repository root walked into an operator's virtualenv sitting
beside the source and rewrote its third-party files. Ruff excludes `.venv` by default and
does not exclude `venv`. `[tool.ruff] exclude` now fences every virtualenv shape, and
`tests/test_formatter_fence.py` finds them by their **`pyvenv.cfg` marker rather than by
name** — a name-based fence catches `venv` and `.venv` and misses `trial-env`, which is the
miss class that caused it.

*A recursive tool's path argument is a claim about everything beneath it.*
