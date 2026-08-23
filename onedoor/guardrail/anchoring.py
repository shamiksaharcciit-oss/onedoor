"""Merkle anchoring, and the two artifacts that leave the store (ND-017 / M2–M4).

**An anchor is worth exactly the independence of where it lives** (R038 §4). A root
stored beside its leaves proves internal consistency and nothing more — the same shape
as the keyring one level down, and `self_consistent` is the word already waiting for it.

So the deployer publishes a small, self-contained **anchor object** somewhere the store
does not control, and a third party holding **only that root and one receipt export**
verifies membership with nothing else of ours.

X-8 fixes the order
-------------------
*Anchor only what you have re-verified.* Sealing is: **verify the chain over the range →
compute the root → write the anchor → publish**. The verification is not decorative. An
anchor over a broken chain would publish a root that certifies damage, permanently and
in public.

A finding the append-only table forced
--------------------------------------
**`anchor_ref` can never be written.** It is a column on `actions_audit`, anchoring
necessarily happens after a row is sealed, and the `actions_audit_no_update` trigger
forbids `UPDATE` — verified against a live store, not assumed. So a row does not point
at its anchor; the **anchor points at a range of rows**, and membership is resolved by
looking up which anchor covers a row's `seq`.

That is the better shape anyway: a back-reference would have been a second answer to a
question the range already answers (X-14), and it would have needed a writable column on
the one table whose value is that it cannot be written.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from onedoor._vendor.canonical import inclusion_proof, merkle_root, verify_inclusion
from onedoor.guardrail import chain
from onedoor.store.clock import to_iso

ANCHOR_SCHEMA = "onedoor/anchor/1"
RECEIPT_SCHEMA = "onedoor/receipt/1"
CADENCE_KEY = "anchor.cadence"
"""Where cadence declares (R040 §2): the ANCHORING configuration, never the deciding
instrument. Cadence schedules anchoring, not deciding, and putting it in `I` would
re-identify the deciding instrument for every row after an ops-schedule tweak."""

DEFAULT_CADENCE = "manual"


class AnchorError(RuntimeError):
    """Sealing was refused. X-8: never anchor what has not been re-verified."""


@dataclass(frozen=True)
class Anchor:
    """One published root, covering a contiguous range of chained rows."""

    root: str
    tree_size: int
    first_seq: int
    last_seq: int
    cadence: str
    sealed_at: str

    def to_object(self) -> dict[str, Any]:
        """The artifact a deployer publishes. One line of JSON.

        A file, an endpoint, a commit, a printed line taped to a wall — **independence
        is the metric, not the medium**, so nothing here cares which.
        """
        return {
            "schema": ANCHOR_SCHEMA,
            "alg": "sha256",
            "tree": "rfc6962",
            "root": self.root,
            "tree_size": self.tree_size,
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
            "cadence": self.cadence,
            "sealed_at": self.sealed_at,
        }


def cadence(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM config WHERE key=?", (CADENCE_KEY,)).fetchone()
    return DEFAULT_CADENCE if row is None else str(row["value"])


def _leaves(conn: sqlite3.Connection, first_seq: int, last_seq: int) -> list[str]:
    return [
        str(r["row_hash"])
        for r in conn.execute(
            "SELECT row_hash FROM actions_audit WHERE seq BETWEEN ? AND ? ORDER BY seq",
            (first_seq, last_seq),
        ).fetchall()
    ]


def seal(conn: sqlite3.Connection, now: datetime) -> Anchor | None:
    """Anchor every chained row not yet covered. Returns None when there is nothing new.

    **X-8, and the order is the point.** The chain is verified first, over the whole
    ledger, and a fault anywhere refuses the seal — because a root computed over a
    damaged chain would certify the damage, and once published there is no taking it
    back.

    Must be called inside the caller's transaction.
    """
    report = chain.verify_chain(conn)
    if not report.sound:
        raise AnchorError(
            "refusing to anchor: the chain does not verify "
            f"({'; '.join(r.detail for r in report.broken)}). X-8 — an anchor over a "
            f"broken chain publishes a root that certifies damage, permanently."
        )

    covered = conn.execute("SELECT MAX(last_seq) AS last FROM anchors").fetchone()
    first_seq = int(covered["last"] or 0) + 1
    last = conn.execute(
        "SELECT MAX(seq) AS seq FROM actions_audit WHERE seq IS NOT NULL"
    ).fetchone()
    last_seq = int(last["seq"] or 0)
    if last_seq < first_seq:
        return None

    leaves = _leaves(conn, first_seq, last_seq)
    anchor = Anchor(
        root=merkle_root(leaves),
        tree_size=len(leaves),
        first_seq=first_seq,
        last_seq=last_seq,
        cadence=cadence(conn),
        sealed_at=to_iso(now),
    )
    conn.execute(
        "INSERT INTO anchors (root, tree_size, first_seq, last_seq, cadence, sealed_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            anchor.root,
            anchor.tree_size,
            anchor.first_seq,
            anchor.last_seq,
            anchor.cadence,
            anchor.sealed_at,
        ),
    )
    return anchor


def anchor_for(conn: sqlite3.Connection, seq: int) -> Anchor | None:
    """Which anchor covers this row? Resolved by RANGE, never by a back-reference.

    `anchor_ref` cannot be written -- see the module docstring -- so the anchor points at
    the rows rather than the rows at the anchor.
    """
    row = conn.execute(
        "SELECT * FROM anchors WHERE ? BETWEEN first_seq AND last_seq", (seq,)
    ).fetchone()
    if row is None:
        return None
    return Anchor(
        root=str(row["root"]),
        tree_size=int(row["tree_size"]),
        first_seq=int(row["first_seq"]),
        last_seq=int(row["last_seq"]),
        cadence=str(row["cadence"]),
        sealed_at=str(row["sealed_at"]),
    )


def receipt_export(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """The artifact that travels — and it is NOT the row.

    A third party verifying membership needs the leaf digest, its index, the tree size
    and the audit path. **None of those is in `actions_audit`**: the row knows its own
    hash and nothing about the tree. So the exported receipt carries the proof with it,
    and that is what makes the acceptance possible at all — a verifier holding this file
    and a published root needs nothing else of ours.
    """
    seq = row["seq"]
    if seq is None:
        raise AnchorError("an unchained row has no membership to prove")
    anchor = anchor_for(conn, int(seq))
    inclusion: dict[str, Any] | None = None
    if anchor is not None:
        leaves = _leaves(conn, anchor.first_seq, anchor.last_seq)
        index = int(seq) - anchor.first_seq
        inclusion = {
            "index": index,
            "tree_size": anchor.tree_size,
            "path": inclusion_proof(index, leaves),
        }
    return {
        "schema": RECEIPT_SCHEMA,
        "row_hash": row["row_hash"],
        "seq": int(seq),
        "e_digest": row["e_digest"],
        "i_digest": row["i_digest"],
        "t_digest": row["t_digest"],
        "v_digest": row["v_digest"],
        "sig": row["sig"],
        "key_id": row["key_id"],
        "alg": row["alg"],
        "anchor": None if anchor is None else anchor.to_object(),
        "inclusion": inclusion,
    }


# --- The standalone verifier (M4) --------------------------------------------------


def _degenerate_path_refusal(inclusion: dict[str, Any]) -> str | None:
    """Refuse the empty-path degeneracy **before any Merkle computation** (R041, F1).

    An RFC 6962 inclusion proof with an empty audit path degenerates to the claim *the
    leaf is the root*. That is legitimately true in exactly one tree — size 1, index 0 —
    and presented with any other `tree_size` it is a forgery that "checks" without a
    single hash computation.

    The law R041 states, and the reason this runs first:
    **a verifier must refuse the degenerate case before it computes, because the
    degenerate case is the one that computes to true.**

    Provenance, owed and recorded rather than re-derived later: this is the degenerate
    empty-path rule of draft-schrock-ep-authorization-receipts-12 §7.3 (Schrock, EMILIA
    Protocol, August 2026), which pins it with two public reject vectors.

    **What delivery measured before adopting it, stated so nobody later mistakes this
    guard for the only line of defence — or for decoration.** Against the vendored RFC
    6962 construction both sabotage vectors already fail, for two independent reasons:
    `verify_inclusion` rejects `index` outside `[0, tree_size)`, and its terminal
    `sn == 0` check fails an empty path whenever `tree_size > 1`. On top of that,
    `_leaf_hash` applies the `0x00` prefix, so a size-1 root is `sha256(0x00 ‖ leaf)` and
    never the bare leaf digest — the literal "root rewritten to the leaf hash" forgery
    cannot verify here at all.

    So this is **defence in depth at the boundary we own**, not a patched hole. It
    belongs here anyway: `check_membership` is our verifier's front door and the vendored
    function is an implementation it delegates to, a re-vendor could arrive without the
    length check, and a third party building from `docs/receipt-digests.md` needs the
    rule stated rather than inherited by luck. It also makes the OUTCOME precise — an
    internally inconsistent artifact is `failed` by definition, not merely a proof that
    happened not to recompute.
    """
    path = inclusion.get("path")
    if not isinstance(path, list) or path:
        return None  # a non-empty path proceeds to the normal recomputation, unchanged

    size = inclusion.get("tree_size")
    index = inclusion.get("index")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        return (
            f"an empty audit path with tree_size={size!r}: the proof claims the leaf is "
            f"the root, which is true only in a tree of size 1"
        )
    if size != 1:
        return (
            f"an empty audit path claims a tree of size {size}: with no siblings the "
            f"proof asserts the leaf IS the root, which is true only at size 1"
        )
    if index != 0:
        return (
            f"an empty audit path at index {index!r}: the only leaf of a size-1 tree is at index 0"
        )
    return None


MEMBERSHIP_VERIFIED = "verified"
MEMBERSHIP_SELF_CONSISTENT = "self_consistent"
MEMBERSHIP_ABSENT = "absent"
MEMBERSHIP_UNVERIFIABLE = "unverifiable"
MEMBERSHIP_FAILED = "failed"


def check_membership(receipt: dict[str, Any], published_root: str | None) -> tuple[str, str]:
    """Does this receipt belong to that root? Returns `(outcome, detail)`.

    **Takes only the two artifacts.** No database, no connection, no import of anything
    that reads a store — which is the acceptance shape R039 named, and the reason this
    function's signature is what it is.

    `published_root` is the trust anchor: a root the caller obtained from **outside** the
    store. Without one, a proof that checks against the root carried *inside* the receipt
    is `self_consistent` — real, and not independence.

    **onedoor never vouches for itself: at the key layer and the anchor layer alike,
    `verified` requires something the store does not hold** (R040 §3).
    """
    anchor = receipt.get("anchor")
    inclusion = receipt.get("inclusion")
    if anchor is None and inclusion is None:
        return MEMBERSHIP_ABSENT, (
            "not anchored yet. Anchoring is periodic, so a recent receipt is normally "
            "un-anchored and that is not a fault"
        )
    if anchor is None or inclusion is None:
        return MEMBERSHIP_UNVERIFIABLE, "the receipt carries half a membership claim"

    leaf = receipt.get("row_hash")
    if not isinstance(leaf, str):
        return MEMBERSHIP_UNVERIFIABLE, "the receipt has no leaf digest to prove"

    degenerate = _degenerate_path_refusal(inclusion)
    if degenerate is not None:
        return MEMBERSHIP_FAILED, degenerate

    stored_root = str(anchor.get("root"))
    if not verify_inclusion(
        leaf,
        int(inclusion["index"]),
        int(inclusion["tree_size"]),
        list(inclusion["path"]),
        stored_root,
    ):
        return MEMBERSHIP_FAILED, "the inclusion proof does not check against the anchor's root"

    if published_root is None:
        return MEMBERSHIP_SELF_CONSISTENT, (
            "the proof checks against the root carried in this receipt; supply the "
            "published root to verify"
        )
    if published_root != stored_root:
        return MEMBERSHIP_UNVERIFIABLE, (
            "the receipt names a different root from the one you published"
        )
    return MEMBERSHIP_VERIFIED, "membership proved against the root you supplied"


def verify_files(receipt_path: str, anchor_path: str | None) -> tuple[str, str]:
    """The whole third-party check: two files, nothing else.

    Deliberately a thin wrapper over `check_membership`, so the acceptance test can run
    it in a directory containing exactly those two files. If this ever needs the
    database, the design has failed R038 §4's independence metric.
    """
    with open(receipt_path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    published: str | None = None
    if anchor_path is not None:
        with open(anchor_path, encoding="utf-8") as handle:
            published = str(json.load(handle)["root"])
    return check_membership(receipt, published)
