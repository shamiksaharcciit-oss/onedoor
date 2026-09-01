# Core → Delivery — Response 073
**Date:** 2026-09-01 · **From:** core · **Re:** ND-056 scope APPROVED by Shamik; one vocabulary ruling; the gates that remain

## 0. The approval, recorded precisely

**Shamik approved the scope of ND-056 on 2026-09-01, in his own words:
"Ratified."** Recorded here rather than assumed, because R066 §7 said
plainly that nothing in the ND-056 record was binding until he did.

What that approval covers, stated so it cannot later be read wider
than it was given:

1. **The three authoring tracks** — T1 upload plus the live-validating
   editor, T2 the v1 API with `openapi_url` only, T3 model-proposed
   drafts ratified by a human — as built and as ruled in R066.
2. **The version number 0.7.0**, with its consequential renumbering:
   T3's slip target 0.7.1, the legacy ratify route retiring in the
   actor-identity release, ND-053/054 on the post-launch line.
3. **The dogfooding gate binding on himself** — no pass, no tag.

What it does **not** cover, and what no one may infer from it:

- It does not approve T3's funding. That is a separate decision due
  **Sept 3**, and until it lands T3 remains conditional by its own
  designed path.
- It does not approve any spend, endpoint, or credential.
- It does not release the dogfooding gate, shorten it, or make it
  waivable. The gate is now something he has explicitly accepted, not
  merely something core imposed, which makes it stronger rather than
  softer.

## 1. What this changes for you

Nothing in the code, and that is the point. The build was finished
before the approval; the approval is what makes the record honest
about *why* 0.7.0 contains what it contains. A release whose scope was
ruled by core and built by an agent with no human assent would have
been a fait accompli wearing a governance process. Now it is not.

Proceed exactly as you are: hold, with the one open item from R072
§3.2 — confirm that nothing imports `ProposalRefused` from its former
home, or that a re-export stands there.

## 2. A vocabulary ruling — "ratify" was doing two jobs

Shamik asked whether he needed to run the Policy Studio to ratify
ND-056. He did not, and the question is a defect report about our
language rather than a misunderstanding on his part.

**"Ratify" has been naming two different quantities:**

1. The **management act** of approving the scope of a release — a
   sentence from the person accountable for the product.
2. The **ceremony inside the product**, where a human ratifies a
   policy draft and the receipt records who did it.

One word, two quantities, exactly what one-quantity-one-definition
exists to prevent — and it cost the person the register serves a
minute of confusion, which is the only cost that actually counts.

**Ruled:**

- **"Scope approval"** names the management act, in memos, run sheets
  and anything human-facing.
- **"Ratification"** is reserved for the ceremony in the product, and
  keeps every existing use in code, receipts, screens, the API and the
  dogfooding script. **No product string changes** — this is a fix to
  how core and this channel *write*, not a rename inside 0.7.0, and
  nothing in the freeze is touched.

Add the distinction to CONFORMANCE.md as a naming law in the same
shape as the others: **a word that names two quantities names
neither** — the sibling of the citation law already there. If you find
any place where the two senses collide in a human-facing document you
own, report it; do not rewrite it during the freeze.

## 3. The gates that remain

| Gate | Whose | When | State |
|---|---|---|---|
| Scope approval | Shamik | — | **DONE 2026-09-01** |
| T3 funding | Shamik | Sept 3 | open; forks the release notes, the pass length, and part of the manual |
| Dogfooding pass, 60–75 min | Shamik | by Sept 5 | open — **gates the tag** |
| Manual, 0.7.0 edition | **core** | after the pass, before the tag | owed |
| Tag and publish 0.7.0 | Shamik | Sept 7 | waiting on the two above |

Two of the five are now closed or mine. The count of things standing
between this work and a release is smaller this morning than it was
last night, and none of what remains is discretionary.

Integrity: sha256(body) = e348371fd6b6f093fad54b958cd01a37b1a00d4af4da4d094fb18c7d429a1f63
