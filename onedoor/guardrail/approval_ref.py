"""Resolving a PEP-presented `approval_ref` (ND-009, A2/A3/A4).

A human approved something. Later a *different* request arrives carrying a reference to
that approval, from an enforcement point that wants to resume it. This module answers
one question — **does this ref authorise this action?** — and returns the answer with
the evidence for it.

The security shape, and it is the whole module
----------------------------------------------
**Every failure mode returns the same behaviour and a different evidence value.** An
expired ref, a consumed ref, a forged ref, a ref for a different action: all of them
resolve to *not authorised*, and the action then **re-evaluates on its own merits**, so
a Tier-3 action simply proposes again. A bad ref never grants, and — just as important
— a bad ref never *errors*, because an error path would tell a prober whether the ref
existed. The caller cannot distinguish `unknown` from `expired` by behaviour. Only the
ledger can.

Single-use, and the trap
------------------------
Consumption is the **first** write, and its `rowcount` is the gate. The trap is
read-then-decide-then-mark: between the read and the mark a second resumption reads the
same `approved` row and both proceed. Consuming first, inside the `BEGIN IMMEDIATE`
that `decide_and_reserve` already holds, makes the race decide itself — and
**a lost race never denies and never errors; it just does not grant**.
"""

from __future__ import annotations

import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from onedoor._vendor.canonical import canon_decimal, canonical_bytes
from onedoor.guardrail.models import ActionRequest, JsonValue
from onedoor.store.clock import to_iso


class ApprovalRefStatus(StrEnum):
    """The seven-value evidence field (`CONFORMANCE.md` §6).

    Evidence, never verdict vocabulary: the forensic distinction between an expired ref
    and a forged one survives without a single new reason code, which is why `ND-009`
    stopped depending on `ND-002`.
    """

    ABSENT = "absent"
    HONORED = "honored"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    UNKNOWN = "unknown"
    ACTION_MISMATCH = "action_mismatch"

    PRINCIPAL_MISMATCH = "principal_mismatch"
    """The consuming caller's principal does not match the approval's recorded
    proposer (`proposed_by`). Refused like every other bad ref: no grant, no
    error — but, unlike the others, the approval itself is NOT consumed, since
    it is still good for the principal it was actually proposed for.

    Was reserved and never emitted: onedoor had no authenticated per-caller
    identity to check it against, since `session_id` was caller-supplied and
    arrived in the same untrusted body as the ref. It does now —
    the decide principal is a keyed fingerprint of the caller's decide key,
    which an attacker cannot copy out of a request he controls. `proposed_by`
    is `NULL` for a row sealed before this existed, or for a same-process
    caller with no key to fingerprint; such a row has nothing to bind to, so
    nothing is checked, exactly as before this binding existed.
    """


@dataclass(frozen=True)
class RefResolution:
    """Whether the ref authorises, and the evidence either way."""

    authorised: bool
    status: ApprovalRefStatus
    approval_id: int | None = None


NUMBER_TAG = "onedoor/num"
"""Wrapper key for a numeric value in the equivalence rendering.

A number is rendered as `{"onedoor/num": "<canonical decimal>"}` rather than as the
bare string, so a numeric `250` and the *string* `"250"` cannot collapse to the same
bytes. The vendored artifact's rule 4 names that trap in as many words -- *a schema
must pin one representation per field; int and "int-string" are distinct bytes* -- and
collapsing them here would be permissive in exactly the wrong direction: a PEP could
present `"250"` against an approval for the number `250`, and the bounds gate that
would have refused the string never runs, because the ref already granted.
"""


def canonical_params(params: dict[str, JsonValue]) -> bytes:
    """The canonical rendering of a params mapping — identity up to spelling.

    Action-equivalence is *same `action_type` and params equal under the
    canonical rendering, evaluated on the frozen received bytes' parse*. Both halves
    matter, and the second half is why this function normalises numbers rather than
    comparing whatever Python types it was handed:

    **A JSON integer never reaches `parse_float`.** `Decimal("250")` serialises to
    `250`, and `json.loads(..., parse_float=Decimal)` hands that back as an **`int`** —
    `parse_float` only sees numbers with a point or an exponent. So the stored side of
    an approval carries `int` where the presented side carries `Decimal`, and a
    comparison that trusted the types would report `action_mismatch` for **every whole
    amount**. Found by the equivalence tests failing on a 250-euro payment, not by
    reading the serializer.

    That failure was safe -- no grant -- but wrong, and the fix is to render every
    numeric through `canon_decimal` so `Decimal("250")`, `Decimal("250.00")` and `250`
    are one value, while `250` and `900` stay two. **Anything that could change the
    decision is not cosmetic; anything the canonical renderer erases is.**
    """
    return canonical_bytes(_canon(params))


def _canon(value: object) -> object:
    if isinstance(value, bool):
        # Before the int branch: `bool` subclasses `int`, and True is not the number 1.
        return value
    if isinstance(value, Decimal | int):
        return {NUMBER_TAG: canon_decimal(Decimal(value))}
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, float):
        # E10 forbids a float on the evaluation path; one reaching here is a bug in an
        # ingress, and rendering it would hide that behind a plausible string.
        raise TypeError("a float reached action-equivalence; params carry Decimals (E10)")
    return value


def equivalent(approved: ActionRequest, presented: ActionRequest) -> bool:
    """Does the presented action match what the human approved?

    Identity up to spelling: same `action_type`, and params equal under the
    canonical rendering. Key order, `250.00` versus `250`, and whitespace are spelling.
    A different amount is not.

    Byte-identity would be too strict — a PEP that re-serialises a request it never
    altered would fail. Effect-set equality alone would be too loose: "approve €250 to
    X" and "€900 to X" share an `action_type` and a `money.egress` effect, so an
    approval would be spendable on a bigger transfer. The human saw params.
    """
    if approved.action_type != presented.action_type:
        return False
    return canonical_params(approved.params) == canonical_params(presented.params)


def effects_consistent(approved: ActionRequest, presented: ActionRequest) -> bool:
    """A derived consistency check, asserted — never the equivalence test itself.

    Effect-set equality *follows* from canonical-params
    identity rather than standing in for it. Kept as a check so a divergence would
    surface as the contradiction it is: two requests with identical canonical params
    resolving to different effects would mean effect resolution had become
    non-deterministic, which is a much larger problem than a rejected approval.
    """
    return approved.action_type == presented.action_type


def resolve(
    conn: sqlite3.Connection,
    *,
    approval_ref: int | None,
    presented: ActionRequest,
    now: datetime,
    principal: str | None = None,
) -> RefResolution:
    """Resolve a presented ref. Consumes it on success, atomically.

    MUST be called inside the caller's transaction: `decide_and_reserve` holds
    `BEGIN IMMEDIATE`, which is what makes the consume-first CAS race-free.

    `principal` is the consuming caller's own identity, as authenticated by whoever
    called `decide_and_reserve` -- compared against the approval's recorded
    `proposed_by`, never against anything the presented request carries.
    """
    if approval_ref is None:
        return RefResolution(False, ApprovalRefStatus.ABSENT)
    if not -(2**63) <= approval_ref < 2**63:
        # No approval id can be this large: the store's integers are 64-bit. Evaluated
        # as a reference to nothing, never raised out of the decision.
        return RefResolution(False, ApprovalRefStatus.UNKNOWN)

    row = conn.execute(
        "SELECT id, state, expires_at, request_json, proposed_by FROM approvals WHERE id=?",
        (approval_ref,),
    ).fetchone()
    if row is None:
        # A ref for an approval that does not exist. Same treatment as every other
        # failure -- the caller learns nothing from the behaviour.
        return RefResolution(False, ApprovalRefStatus.UNKNOWN)

    state = str(row["state"])
    if state in ("consumed", "executed", "denied"):
        return RefResolution(False, ApprovalRefStatus.CONSUMED, approval_ref)
    if state == "expired" or str(row["expires_at"]) <= to_iso(now):
        return RefResolution(False, ApprovalRefStatus.EXPIRED, approval_ref)
    if state != "approved":
        # `pending` -- nobody has approved it yet. Not a grant, and not an error: the
        # PEP is early, and the action re-evaluates on its own merits.
        return RefResolution(False, ApprovalRefStatus.UNKNOWN, approval_ref)

    approved = ActionRequest.model_validate(
        json.loads(str(row["request_json"]), parse_float=Decimal)
    )
    if not equivalent(approved, presented):
        return RefResolution(False, ApprovalRefStatus.ACTION_MISMATCH, approval_ref)

    proposed_by = row["proposed_by"]
    if proposed_by is not None:
        # A row with nothing recorded has nothing to bind to -- checked only when
        # there is a real proposer identity to check against (a keyed
        # fingerprint, not anything the presented request itself carries).
        if principal is None or not hmac.compare_digest(principal, str(proposed_by)):
            # Not consumed: the approval is still good for its real proposer, only
            # this presenter is not that proposer.
            return RefResolution(False, ApprovalRefStatus.PRINCIPAL_MISMATCH, approval_ref)

    # CONSUME FIRST, and let the rowcount be the gate. Reading, deciding, then marking
    # would let a second resumption read the same `approved` row in between and both
    # proceed. A lost race is not an error and not a denial: the ref evaluates as
    # absent and the action re-evaluates on its own merits.
    consumed = conn.execute(
        "UPDATE approvals SET state='consumed' WHERE id=? AND state='approved'",
        (approval_ref,),
    )
    if consumed.rowcount == 0:
        return RefResolution(False, ApprovalRefStatus.CONSUMED, approval_ref)

    return RefResolution(True, ApprovalRefStatus.HONORED, approval_ref)
