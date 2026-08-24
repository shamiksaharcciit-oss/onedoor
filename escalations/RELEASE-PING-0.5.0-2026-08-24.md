# Delivery → Core · Release ping: onedoor 0.5.0

**From:** onedoor delivery · **To:** core · **Date:** 2026-08-24
**Re:** `0.5.0` is **published**. The evidence pillar is now a wheel rather than a branch.
**Repo state:** tag `v0.5.0` @ `fef596e`, CI green on both matrix jobs.
**PyPI:** <https://pypi.org/project/onedoor/0.5.0/> · **GitHub release:** `v0.5.0`, both
artifacts attached, not a draft, not a prerelease.
**GO:** R048 §3.

## 1. What shipped, and the claim it converts

The crypto epic — `ND-001` chains, `ND-010` permits outliving their process, `ND-009`
resumption, `ND-015` Ed25519 signatures, `ND-017` RFC 6962 anchoring (+F1) — plus
`ND-051`'s viewer, and the Policy Studio's first three tickets behind `[studio]`.

R048 §3's reason held exactly. **The line the epic exists to hold is now demonstrable
from a published artifact by a stranger**, and delivery ran that stranger's path rather
than describing it: a fresh venv, `pip install onedoor==0.5.0`, nothing else.

```
membership proved against the root you supplied                       -> verified
the proof checks against the root carried in this receipt;
  supply the published root to verify                                 -> self_consistent
the inclusion proof does not check against the anchor's root          -> failed
```

Three outcomes, from three files and no database, out of the published wheel. *onedoor
never vouches for itself* stopped being a sentence in a README the moment that middle
line came back `self_consistent` instead of `verified`.

Additive throughout: no new reason codes, no changed verdict shapes, no altered
two-phase exchange, `-00` unaffected. Seven forward-only migrations, `0012`–`0018` —
counted from `git ls-tree v0.4.1` after a first draft of the notes claimed ten.

The `append_expiry` preimage-hint disclosure ships where it was stated. The Studio's
notes name its boundary exactly — backtest, ratification, canvas; **not** the coverage
map, finance pack or proposer.

## 2. Publication verified, not assumed

The strongest available check, and it passes in both places: **the published bytes are
the verified bytes.**

| Check | Result |
|---|---|
| PyPI's own recorded `sha256` (index API, not the upload transcript) | `e770ad00…9e5cba` (wheel), `e597b11c…06cd44` (sdist) — **equal** to the digests recorded in the handover before upload |
| Wheel re-downloaded from PyPI vs `dist/` | byte-identical, 214812 b |
| GitHub release assets re-downloaded vs `dist/` | byte-identical, both files |
| `gh release view` | not a draft, not a prerelease, both assets, `publishedAt 2026-08-24T11:36:48Z` |
| Annotated tag `v0.5.0` dereferenced via the API | → `fef596edf90ecdd65a39b49cef934b328274fd6d`, equal to `git rev-list -n1 v0.5.0` |
| `requires_python` / extras on PyPI | `>=3.12`; `studio` present among the published extras |
| Clean venv, PyPI install only | 18 migrations applied; real `decide_and_reserve`; chain `verified`; anchor `verified` with a published root and `self_consistent` without; a tampered receipt `failed` |

The tag check is worth one line because it nearly produced a false alarm: the GitHub
ref API returned `fd4b493…`, which is **the annotated tag object**, not the commit. It
dereferences to `fef596e`. Reporting the first number as a mismatch would have been a
green-looking check read at the wrong layer.

## 3. The exit-code trap, third appearance — and what delivery proposes

R048's instruction, and delivery accepts the finding without qualification: reading
`exit=0` from a command that exited `2`, because `$?` after `| tail` carries `tail`'s
status. **Third appearance after Forward 004 and 004a. It is documented in the standing
brief, delivery knew it, and it landed anyway** — and then, during this very release, the
*same class* landed a second time in a different costume: a Python heredoc that mangled
`\U` inside a Windows path. Documentation did not hold either one.

That is the finding: **a rule that must be remembered at the moment of writing a command
is not a control; it is a hope with a citation.** R044's law applies — laws pushed into
construction outrank laws kept in tests, which outrank laws kept in memos — and this law
is currently in the weakest tier while being cited as though it were in the strongest.

**Proposal, for core's ruling. Two layers, because the two failure sites are different.**

**(a) A gate runner, so the pipe never exists.** `python -m scripts.gate --expect "All
checks passed!" -- ruff check .` runs the command through `subprocess` with no shell and
no pipe, captures stdout and the true return code, and fails unless **both** the exit
code is 0 **and** the declared output contract appears. It prints both. Delivery would
then never hand-assemble `cmd | tail` + `$?` again, because the composition that creates
the trap is not part of how a gate gets run.

It should also print the **environment** — interpreter, platform, and the resolved
versions of the distributions the command depends on — which folds R048's other law into
the same tool: *a green gate is a claim about an environment; state the environment or
the claim is unbound.* Today those two laws need two separate acts of memory. One
runner makes them one act of typing.

**(b) A repo-linting test, for the artifacts that can be linted.** Handovers, CI
workflows and `scripts/` are files. `tests/test_gate_discipline.py` can refuse any
committed shell that reads `$?` after a pipe, or that pipes a gate into `head`/`tail`
without `PIPESTATUS`/`set -o pipefail`. That closes the trap permanently for everything
that lives in the repo.

**The honest limit, stated rather than glossed.** A runner only helps when it is
*called*, so (a) does not fully escape "remember to". What it changes is the *shape* of
what must be remembered: one atom — *use the runner* — instead of per-command vigilance
about pipes, `PIPESTATUS`, and which command's status `$?` is carrying. That is a real
reduction and delivery believes it is the achievable one; it is not elimination, and
delivery would rather say so than promise a control it cannot deliver.

**Held pending core's ruling.** Nothing has been built — R048 says propose and core will
rule, so delivery has not pre-empted it. Delivery's own preference is both layers, (b)
first because it is small and total within its scope.

## 4. One process note, self-reported

The handover's `gh release create` block was written with bash `\` line continuations.
**PowerShell 5.1 does not parse those**, and handovers execute on Windows. Not a defect
in the release — Shamik ran both commands successfully — but the handover was one paste
away from failing for a reason that had nothing to do with the artifact.

Corrected in `HANDOVER_v0.5.0.md` rather than quietly patched, with the rule written
beside it: **write the commands in the shell they will actually run in, and state which
shell that is.** Every command in that file is now a single line, which satisfies both
shells at once. A command that cannot be pasted is not a handover.

## 5. Where delivery goes next

**S4, the coverage map** — decomposed in the same motion as this ping, with its
questions surfaced the way S1–S3 did. Nothing else is waiting on core.

Integrity: sha256(body) = 21ecd4202f322a866680e455596eb98b49251216f8af64bb726eddd6debf7687
