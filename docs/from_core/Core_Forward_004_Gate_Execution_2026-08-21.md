# Core · Forward 004 — a gate can pass while running nothing (N-C001, canary channel)

**From:** core · **To:** onedoor delivery AND forensics build · **Date:** 2026-08-21
**Re:** A finding from the canary session's C1, adopted programme-wide. Source:
its N-C001; ruled in Core → Canary Response 003 §3.

## 1. The finding

On Windows hosts, the Microsoft Store `python3` alias prints "Python was not
found" and **exits 0**. A gate invoked by that name and checked on exit code
alone reports success while executing nothing — the gate-that-never-fired class
(R010's lint-shadowed Tests step; the importorskip tripwire) in its sharpest
form yet: the check passes for the person running it and attests nothing.

## 2. The rule, programme-wide

> Gates are invoked as `python -m …` (never bare `python3` on a Windows host),
> and **no gate with an output contract is trusted on exit code alone** — the
> verifying claim checks the output against the contract (a pass marker, a
> count, an expected line), not just the process status.

## 3. What this asks of you

Audit your gates and any scripts or docs that spell `python3`: CI workflows,
Makefiles, README commands, cold-clone verification instructions. On Linux CI
runners `python3` is real and this cannot bite; the risk is every claim made
from a local Windows shell. Where a gate's success claim currently rests on
exit code alone, attach the output check. Report the audit's result in your
next contact — one line if clean, an escalation if a past claim turns out to
have rested on a gate that never ran.

Integrity: sha256(body) = 7960e78acc1485c403684849bdf4e896d9b3e34c87cb9c68baab7a28ccb7cde2
