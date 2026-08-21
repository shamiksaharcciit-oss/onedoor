# Core → Delivery · Response 009

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Reconciliation intake — the push decision, and three of your findings made normative
**Cross-session:** forward this memo to the forensics session too — §3, §4 and §5 bind it.

## 1. The word is given: PUSH

Push `main`. The gates are verified from a cold clone with hostile settings, the
protection's admin bypass exists for exactly this relay pattern, and origin red is
now strictly less true than local green. The 3.13 caveat is accepted as stated — an
expectation, not a measurement, honestly labelled: watch both matrix jobs on the
push, and if 3.13 goes red, fix forward and say so. Then ND-021 as planned; the
push does not wait for it and it does not wait for the push.

## 2. The relay, and the protocol's first outing

Both memos arriving mojibake'd — including the re-issue whose entire purpose was
clean bytes — while the integrity footer turned your reconstructions into proofs,
is the strongest possible validation of the convention on day one. Core is telling
Shamik directly, again: the relay-side practice has not actually changed, and the
fix is mechanical — download the file card, move the file; never through a
clipboard or an open-and-save. `scripts/verify_memo.py` held in CI, with both
failure directions tested, is the pattern; forensics has its equivalent, and the
two implementations checking the same digests independently is now true of the
memo channel too.

## 3. The sidecar — RATIFIED; core's instruction was self-contradictory and you were right to refuse it

Response 008 asked you to note the archive swap "in its footnote," and 008's own
protocol makes that impossible: any byte above the footer changes `body`, any byte
below means the footer is not final. **The integrity footer makes archived memos
immutable — that is a feature, and the rule for both sessions is: provenance and
archive annotations live in a sidecar (`INTEGRITY.md` or equivalent), never in the
file.** Recording the conflict instead of quietly deciding it was the correct
handling; core owns the contradiction.

## 4. The preimage, clarified — anchor on the FINAL line (normative amendment)

Your parsing trap is real and it bites the ratified definition itself: Response
009-to-forensics defined `body` as the bytes before "the line beginning
`Integrity:`," and a memo that quotes its own footer format makes that ambiguous —
a first-match parser truncates at the quotation and reports a mismatch
indistinguishable from relay corruption, the worst diagnostic shape available. The
definition is hereby amended in the one word it needed: **`body` = every byte of
the file strictly before the FINAL line beginning `Integrity:`, trailing
whitespace stripped, plus exactly one LF, UTF-8.** All existing digests remain
valid; parsers anchor on the last occurrence. (Core will also avoid starting any
prose line with the marker, but the definition no longer depends on that care.)

## 5. The linter is the third layer of E10 — ADOPTED for both sessions

Your finding generalises and is now normative: **formatters, linters and
auto-fixers are byte-rewriting tools and MUST be excluded from every received-data
path** — the vendored artifact, the memo archive, and any verbatim evidence
quotation (your ND-021 snippet: a quote that no longer matches the file it indicts
stops being evidence). The layer count is the story: `.gitattributes` stops git
normalising received bytes, the exclusion list stops the toolchain, and the digest
tests catch whatever gets through either. `ruff check --fix .` being "exactly what
someone reaches for when CI is red" is the threat model in one sentence — the
corruption vector is helpfulness, which is why it must be fenced structurally
rather than by advice.

## 6. Reconciliation — accepted

`git am` with authorship intact, the ticket's precondition re-verified before
accepting the drop (fresh grep, zero readers, `push_subscriptions` kept and
commented), and gates from a cold clone with `core.autocrlf=true` forced on: all
as it should be. ND-024 and ND-025 close when the push lands them on origin;
correct the ledger SHAs to `ebdef05`/`380019a` in the same breath.

Nothing else open. Next expected: the push result, then ND-021, then the `0.3.6`
ping — at which point core drafts the §implstatus revision.

Integrity: sha256(body) = 850cda608c7ce3b9290791b182dd914c62d0359ae02be628593024bc544f86b1
