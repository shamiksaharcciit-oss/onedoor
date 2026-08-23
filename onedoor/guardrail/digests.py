"""The four receipt digests: `E`, `I`, `T`, `v` (ND-017 / M1).

**The normative definition is `docs/receipt-digests.md`.** This module implements it;
`tests/guardrail/test_receipt_digests.py` holds a second implementation written from
that document rather than from this code — the P2-06 pattern `docs/row-preimage.md`
already carries, because a definition nobody else has built from is a description of one
function's behaviour.

Signed off by R040 §1 with two amendments, both in the direction delivery's flags
pointed. **Frozen from the first sealed row.**

What the four mean
------------------
Read from the vendored `manifest.schema.json` rather than invented, and confirmed by
arithmetic: the artifact's shipped `t_digest` is `4f53cda1…b945`, which is SHA-256 of
canonical `[]` — so `T` really is a declared closure and not a bag of facts.

``E``  the sealed evidence — what the decision was made *from*
``I``  the instrument — what *did* the deciding
``T``  the trust set — what you must **trust** to accept the verdict
``v``  the verdict itself

`E`, `I` and `T` stay **opaque digests** in the receipt, never inlined structures,
because `I` will generalise from verdict-instruments to stage-attribution instruments
and inlining would re-hash frozen rows on an append-only table.

Two amendments worth their own paragraph
----------------------------------------
**`T` does not carry `policy_source`.** The policy hash already lives in `E` as
`policy_version`, where it is an *input identity* — what was in force. Carrying the same
hash in two preimages would be two answers to one question at the exact layer where
drift becomes undetectable: X-14, inside the seal itself. What `T` owes a verifier is
what must be **trusted**, and `closure` says it.

**`I` does not carry the anchor cadence.** Delivery flagged the consequence — a cadence
change would re-identify the deciding instrument for every row after it — and R040 §2
ruled the consequence was the defect rather than the point: cadence schedules
*anchoring*, not *deciding*, so it declares in the anchoring configuration and is
recorded on the **anchor object**, where a change is visible in exactly the artifact
stream it governs. `I` keeps only what did the deciding.

No `len8` anywhere
------------------
Every digest is SHA-256 over `canonical_bytes` of a canonical object, so **no
concatenation appears and the length-prefix dialect is not reached**. Said plainly
rather than decorated with an unused framing: R039 asked for `len8` *where concatenation
appears*, and a canonical object needs none.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from onedoor._vendor.canonical import canonical_bytes, digest_bytes

EVIDENCE_KIND = "onedoor/decision-evidence/1"
INSTRUMENT_KIND = "onedoor/decision-instrument/1"
TRUST_KIND = "onedoor/decision-trust/1"
VERDICT_KIND = "onedoor/decision-verdict/1"

STORE_CLOSED = "store-closed"
"""Nothing external vouches: a verifier is trusting this store for the resolution."""

ANCHOR_CLOSED = "anchor-closed"
"""This deployment publishes Merkle roots, so a verifier can close the trust set on a
root held outside the store rather than on the store itself."""


class RowLike(Protocol):
    """What the digest builders need: subscripting and `keys()`.

    A `sqlite3.Row` satisfies it, and so does the writer's not-yet-inserted mapping --
    which it must, because these columns live on an append-only table and a column that
    cannot be UPDATEd has to be right when the row is born or it is never right at all.
    """

    def __getitem__(self, name: str) -> Any: ...

    def keys(self) -> list[str]: ...


def _digest(obj: dict[str, Any]) -> str:
    """SHA-256, lowercase hex, over the vendored canonical bytes (artifact rules 4–5)."""
    return digest_bytes(canonical_bytes(obj))


def _field(row: RowLike, name: str) -> Any:
    return row[name] if name in row.keys() else None


def evidence(row: RowLike) -> dict[str, Any]:
    """`E` — what the decision was made from.

    `params_digest` is a digest of the **frozen bytes hashed verbatim**, never the bytes
    inlined and never re-serialised. That is E10's received-data discipline, and it is
    also why a deployer can hand a receipt to a third party **without handing over the
    request body** — the receipt proves what was decided on without disclosing it.
    """
    raw = _field(row, "params_json")
    if raw is None:
        params_digest = None
    else:
        data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        params_digest = hashlib.sha256(data).hexdigest()
    return {
        "kind": EVIDENCE_KIND,
        "params_digest": params_digest,
        "params_provenance": _field(row, "params_provenance"),
        "request_id": _field(row, "request_id"),
        "action_type": _field(row, "action_type"),
        "source": _field(row, "source"),
        "policy_version": _field(row, "policy_version"),
        "snapshot_schema": _field(row, "snapshot_schema"),
    }


def instrument(row: RowLike, *, snapshot_schema: str | None = None) -> dict[str, Any]:
    """`I` — what did the deciding.

    Every identity the engine already records beside a verdict for exactly this reason,
    gathered into one digest: the protocol, the preimage version, the URL canonicaliser
    when one ran, the opaque-host class when one matched, and the policy-snapshot
    renderer.

    **No anchor cadence** (R040 §2). Cadence schedules anchoring, not deciding.
    """
    return {
        "kind": INSTRUMENT_KIND,
        "protocol": _field(row, "protocol"),
        "preimage_version": _field(row, "preimage_version"),
        "canon_schema": _field(row, "canon_schema"),
        "opaque_class": _field(row, "opaque_class"),
        "snapshot_schema": snapshot_schema,
    }


def trust(row: RowLike, *, closure: str) -> dict[str, Any]:
    """`T` — what you must trust to accept the verdict. Never a second copy of `E`.

    `keys` is the signing key this row's signature relies on, as a list because a
    verifier may need more than one when a chain spans a rotation. `closure` declares
    what the trust set closes over: `store-closed` means you are trusting this store,
    `anchor-closed` means a published root vouches.

    Nothing else. `policy_version` is deliberately **absent** — it is an input identity
    and `E` already seals it, and the same hash in two preimages is X-14 inside the seal
    (R040 §1).
    """
    key_id = _field(row, "key_id")
    return {
        "kind": TRUST_KIND,
        "keys": [] if key_id is None else [str(key_id)],
        "closure": closure,
    }


def verdict(row: RowLike) -> dict[str, Any]:
    """`v` — the decision's own content.

    `budget` is carried as its stored canonical JSON text rather than re-parsed: it was
    canonicalised when written (decimals as canonical strings, never floats), and
    re-rendering it here would mean the sealed bytes and the stored bytes could differ.
    """
    return {
        "kind": VERDICT_KIND,
        "decision": _field(row, "decision"),
        "reason_code": _field(row, "reason_code"),
        "nominal_tier": _field(row, "nominal_tier"),
        "effective_tier": _field(row, "effective_tier"),
        "outcome": _field(row, "outcome"),
        "budget": _field(row, "budget_json"),
        "approval_ref_status": _field(row, "approval_ref_status"),
    }


def digests_for(
    row: RowLike, *, closure: str = STORE_CLOSED, snapshot_schema: str | None = None
) -> dict[str, str]:
    """The four digests for one row, ready to write into its columns."""
    return {
        "e_digest": _digest(evidence(row)),
        "i_digest": _digest(instrument(row, snapshot_schema=snapshot_schema)),
        "t_digest": _digest(trust(row, closure=closure)),
        "v_digest": _digest(verdict(row)),
    }
