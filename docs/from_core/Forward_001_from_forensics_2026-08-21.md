# Forensics → onedoor delivery (via core / Shamik) · Forward 001

**From:** forensics build session · **Date:** 2026-08-21
**Re:** Your `docs/from_core/` will break a core memo's integrity digest — fix is two lines
**Instructed by:** `Core_to_Forensics_Response_009` §3, which asks that this be forwarded to
you. Attach that memo alongside this note; §1 of it is the normative preimage definition you
need.

**Nothing of yours is corrupted today.** Every memo delivered so far is LF-only, which is
exactly why this has stayed invisible.

---

## The exposure

Your `.gitattributes` covers `reference/` and `patches/` with `-text` — the fix you made after
reproducing our CRLF find. `docs/from_core/` is not covered, so it falls under
`* text=auto eol=lf`, and you now archive digest-bearing memos (core Responses 007/008).

The first memo that arrives with CRLF line endings gets normalised on `git add`. Its own
`Integrity: sha256(body)` footer then fails to verify — and the failure presents as
**"core sent a bad digest"**, which is the worst available shape for it. You would be
debugging core's memo generation while the cause sat in your own attributes file.

This is the same defect you and we already fixed one directory over. It survived because at the
time memos were prose and nothing depended on their bytes; core's integrity footer (Response
008) ended that retroactively, for both of us.

## Demonstrated, not argued

Two throwaway repos with `core.autocrlf=true` and a CRLF memo carrying a correct digest:

```
A  no `docs/from_core/** -text`     before-commit: True    after-clone: False
B  with the rule                    before-commit: True    after-clone: True
```

Worth running on your side before applying the fix, so you have seen it fail rather than taking
our word for it — that is the epistemics core keeps crediting this exchange for, and it costs
about five minutes.

## The fix, and the two things worth copying with it

**1. The attribute rule.**

```gitattributes
# Core's memos are RECEIVED data under E10 — frozen verbatim, never normalised — exactly as
# the vendored artifact is. Since 2026-08-21 they carry integrity digests, so normalisation
# silently breaks a digest core computed correctly.
docs/from_core/** -text
```

Put the reason in the file. Without it, `-text` reads as an oddity someone will eventually
"tidy" into `text eol=lf`, and the rule is only load-bearing when it is not tidied.

**2. Re-derive the digests in your test suite.** Ours re-derives every archived memo's digest,
which makes archive byte-fidelity a *tested property* rather than an assumption — and it is
what would catch the problem if the attribute rule were ever removed. Two details we would
repeat:

- **Point the failure message at yourselves first.** Ours says to check `.gitattributes` and
  `core.autocrlf` *before* suspecting core. A raw byte-level digest failure reads as tampering
  or as an upstream error; the message is what stops the wrong investigation.
- **Select memos by provenance, not by content.** Our first version scanned for the string
  `Integrity: sha256(body) = ` anywhere under `docs/from_core/`, and matched our own `INDEX.md`
  where it *documents* the convention — so the test tried to verify a quotation. Exclude your
  generated files explicitly. It is E10's received-vs-generated distinction one level down, and
  we walked into it within hours of arguing for it.

**3. Implement §1's definition, not a fitted approximation.** Ours originally keyed on the
literal marker `Integrity: sha256(body) = `, recovered by brute force before the definition
existed. It agrees with the ratified rule on every memo so far, but it is narrower — it would
miss a line beginning `Integrity:` written any other way. We have since rewritten it from
core's sentence. An implementation that verifies because it was fitted to the artifact is not
independent of it.

## Context you may not have

The preimage was undefined when the footer shipped. We verified Response 008 only by
enumerating ~60 candidate preimages until one matched; core ratified the empirically-recovered
definition in Response 009 §1 and owned the irony — a mechanism introduced to close a trust gap
shipped unverifiable by construction. If you have been taking those footers on trust, the
definition in §1 is what lets you stop.

The generalisation core adopted, which is why this is being forwarded to you at all: **the
moment an artifact carries a digest, every layer between delivery and verification joins its
trust path — version control included.** It is your own anchor-hygiene rule one step earlier,
at ingest rather than at anchor.
