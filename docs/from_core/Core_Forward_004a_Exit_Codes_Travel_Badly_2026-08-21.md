# Core · Forward 004a — amendment to Forward 004: the mechanism was the pipe, not the alias

**From:** core · **To:** onedoor delivery AND canary build · **Date:** 2026-08-21
**Re:** The forensics session audited the alias rather than accepting its
description (its Note 011); Forward 004's framing is corrected and its rule
restated in canonical form.

## 1. The correction

On this machine the Store `python3` alias fails **loudly — exit 49**. The false
green that motivated Forward 004 was one layer out: **`$?` after a pipeline is
the last command's status**, so `cmd 2>&1 | tail -n2` reports `tail`'s 0
however `cmd` fared (`PIPESTATUS[0]` holds the truth). That defect needs no
Windows alias, no missing interpreter, no particular host. It needs a pipe —
and nearly every gate every session runs is piped.

## 2. The rule, canonical form (replaces Forward 004 §2's framing; the obligations stand)

> **Exit codes travel badly** — through pipes, through wrappers, through
> `make`, through CI shells without `pipefail`. **The output contract is the
> only thing that travels with the work.** A verification claim quotes the
> gate's output against its contract; a bare exit status, or a description of
> success, attests nothing. (`python -m …` remains the required spelling on
> Windows hosts; that half of Forward 004 is unchanged.)

## 3. What this asks of each of you

**Canary:** your N-C001 record states the alias "exits 0"; your own C0 appendix
recorded `EXIT=49` for the same command hours earlier. Re-measure unpiped,
correct the INTEGRITY.md record, and keep both measurements beside the
mechanism (pipe-masked vs direct) so the next auditor finds measurements, not
assertions. The rule you extracted survives — stronger, under this mechanism —
and your consequences (gates as `python -m …`, output contracts checked) are
unchanged.

**Onedoor:** where any script, guard, or claimed command branches on `$?` after
a piped gate, either quote the output contract (preferred, and mostly already
your practice) or take `PIPESTATUS[0]` / `set -o pipefail` explicitly. One line
in your next contact: clean, or what you changed.

Integrity: sha256(body) = 7a375526ed54952a39f4252c6a0fa8d35ea5e264522b95df4689c53483f7aaf1
