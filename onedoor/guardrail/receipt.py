"""Verification of a decision receipt — the one implementation (ND-051 / V1).

This module exists so that there is **exactly one** answer to "is this receipt
sound?" in the entire package. The viewer imports it; a CLI will import it the day
one exists. Nothing re-implements it, and
`tests/viewer/test_no_second_verification.py` fails if the viewer package so much as
imports `hashlib`.

That structural rule came from the forensics channel and it is not fussiness: a
renderer that computes its own digest for display will, eventually, compute it
slightly differently from the checker, and then the page shows a green tick that the
checker would not give. The page must render **the checker's output**, never its own
opinion.

Four outcomes, never two
------------------------
The programme rule (R010) says *absent*, *unverifiable* and *failed* are distinct and
must never collapse. In a viewer that distinction is the whole product:

``verified``
    Checked, and it holds.
``absent``
    The thing is not there **and is not supposed to be yet**. `row_hash` is NULL in
    `0.4.1` because `ND-001` has not run. That is a fact about the roadmap, not a
    fault, and it renders as a quiet line naming the ticket.

    The wording matters and R030 §3 sharpened it: *"not yet in operation"*, never
    *"not yet produced"*. The second reads like something that should have happened
    and did not — absent-by-schedule wearing the face of broken. A placeholder for a
    future feature has to say which of the two it is, in the words a reader meets, or
    the three-outcome discipline stops at the API boundary and never reaches the
    person it was for.
``unverifiable``
    It should have been checkable and was not — a policy snapshot row that is gone, a
    chain that is half written. **This is a failure to surface, never a skip**, and it
    renders as loudly as an outright failure. Someone has to look.
``failed``
    Checked, and it does not hold.

The difference between ``absent`` and ``unverifiable`` is the difference between "not
yet produced" and "produced and then lost", which is R015's null-versus-empty rule
arriving in a user interface.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from onedoor.guardrail import signing
from onedoor.guardrail.models import Budget, CheckId, LegacyBudget
from onedoor.guardrail.preimage import row_hash_of
from onedoor.guardrail.received import Provenance
from onedoor.guardrail.signing import ALGORITHM

LEGACY_CAP_REASONS = frozenset({"cap_rate", "cap_value"})
"""Deprecated since 0.8.0, never emitted, gone from `CheckId` (nothing constructs
one from a stored string). Named here, as plain strings, only so a row sealed
before 0.8.0 -- never rewritten -- is still recognized for what it is."""

CAP_REASONS = frozenset({CheckId.RATE_EXHAUSTED.value, CheckId.BUDGET_EXHAUSTED.value}) | (
    LEGACY_CAP_REASONS
)
"""The reasons that MUST carry a budget object (E7). A cap denial that cannot name
its window is not re-derivable, which is the whole argument for `budget_json`.
Both the deprecated and the current names: this set decides whether a ROW, old
or new, is a cap denial, so it must recognize a row sealed before 0.8.0 exactly
as readily as one sealed after."""

CHAIN_COLUMNS = ("row_hash", "prev_hash", "seq")
"""ND-001's chain, dark in `0.4.1`. All NULL is `absent`; some NULL is `unverifiable`."""

RETIRED_BEFORE: dict[str, str] = {
    "cap_daily_rate": "aadp/0.1",
    "cap_eur_day": "aadp/0.1",
    "cap_eur_month": "aadp/0.1",
}
"""For each retired code, the ONE protocol stamp a row must carry for that
code to be an honest record rather than a failure -- the code was live
under exactly that protocol, before its own retirement.

`cap_daily_rate`/`cap_eur_day`/`cap_eur_month` retired at 0.4.0, which is also
where the `protocol` column was born: a row with no stamp (read as `aadp/0.1`,
the absent-value rule) can only predate 0.4.0, so it can only predate these
codes' own retirement. That is a real, row-carried marker.

`cap_value`/`cap_rate` are deliberately NOT here. They retired at 0.8.0
WITHOUT a protocol bump -- `AADP_PROTOCOL` has been the literal constant
`"aadp/0.2"` since 0.4.0 and did not change for this switch -- so a row
written the day `cap_value` was born (0.4.0) and a row forged today with the
same reason code both carry the identical `aadp/0.2` stamp. No column on the
row distinguishes them, and the reason-code string itself cannot be used as
its own marker: that is exactly what `reason_vocabulary` is checking, so
using it as evidence for itself would let a forged row excuse itself just by
using an old word. Absent a real marker, a `cap_value`/`cap_rate` row still
reads `failed` here -- unresolved, reported to core rather than guessed at."""

REQUIRED_AUDIT_TRIGGERS = ("actions_audit_no_update", "actions_audit_no_delete")


class Status(StrEnum):
    VERIFIED = "verified"
    SELF_CONSISTENT = "self_consistent"
    """Real information, named for exactly what it is (R038 §1).

    A signature that matches a public key found in THIS STORE'S OWN KEYRING. That is not
    nothing -- the bytes do check out -- and it is not verification either, because an
    attacker with write access to the store supplies both the altered row and the key
    that vouches for it. Calling it `verified` would be the store witnessing itself;
    calling it `unverifiable` would throw away a real check that passed.

    **A receipt system must not be its own witness.** Supply a trusted `key_id` from
    outside the store and the same signature reports `verified`.
    """

    ABSENT = "absent"
    UNVERIFIABLE = "unverifiable"
    FAILED = "failed"
    RETIRED_VOCABULARY = "retired_vocabulary"
    """A reason code retired from the CURRENT build's vocabulary, found on a
    row whose own `protocol` stamp proves it was written before that code's
    retirement. Not a fault -- the row is an honest record of a decision
    this PDP correctly made under the vocabulary live at the time -- but distinct
    from `verified`, because an operator reading a receipt should see that the
    code is no longer current, not just that the row checks out.

    Judged from the row's OWN `protocol` column, never from the reason-code
    string itself (that would be circular: the string is the very thing under
    test, and an attacker forging a row today could simply write an old code
    into it) and never from `created_at` (a received/generated timestamp is not
    a verified claim about when a row was sealed). Where no such marker
    distinguishes "before" from "after" a code's own retirement -- true for
    `cap_value`/`cap_rate`, retired at 0.8.0 without a protocol bump, so every
    row from 0.4.0 onward carries the identical `aadp/0.2` stamp either way --
    this state is not assigned; see `_check_reason_vocabulary`."""


@dataclass(frozen=True)
class Check:
    """One question asked of the store, and the answer."""

    name: str
    status: Status
    detail: str

    @property
    def is_fault(self) -> bool:
        """Does this check stop the receipt from being rendered as sound?

        `unverifiable` counts. That is the point of having four outcomes rather than
        three: a check that could not run is not a check that passed.
        """
        return self.status in (Status.UNVERIFIABLE, Status.FAILED)

    @property
    def is_partial(self) -> bool:
        """True for a check that passed as far as it could and no further.

        `self_consistent` and `retired_vocabulary` are not faults -- nothing is wrong
        -- but neither must be displayed as a plain pass, so the renderer needs a third
        class rather than a boolean.
        """
        return self.status in (Status.SELF_CONSISTENT, Status.RETIRED_VOCABULARY)


@dataclass(frozen=True)
class ReceiptVerification:
    """The checker's whole answer. A renderer shows this; it does not second-guess it."""

    checks: tuple[Check, ...]

    @property
    def faults(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.is_fault)

    @property
    def sound(self) -> bool:
        """True only when nothing is failed and nothing is unverifiable.

        Deliberately not "no failures": an unverifiable check makes a receipt unsound,
        because the alternative is a page that renders values it could not confirm.
        """
        return not self.faults

    def by_name(self, name: str) -> Check:
        for check in self.checks:
            if check.name == name:
                return check
        raise KeyError(name)


def _check_params_byte_form(row: sqlite3.Row) -> Check:
    """Byte form BEFORE any digest (R028).

    A digest computed over bytes nobody looked at is a number about a mystery. If the
    frozen params are not even UTF-8 JSON, say *that* — do not proceed to hash them
    and report a clean-looking mismatch downstream.
    """
    raw = row["params_json"]
    if raw is None:
        return Check("params_byte_form", Status.FAILED, "params_json is NULL")
    data = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return Check("params_byte_form", Status.FAILED, f"not valid UTF-8: {exc}")
    try:
        json.loads(text)
    except ValueError as exc:
        return Check("params_byte_form", Status.FAILED, f"not valid JSON: {exc}")
    return Check("params_byte_form", Status.VERIFIED, f"{len(data)} bytes, valid UTF-8 JSON")


def _check_params_provenance(row: sqlite3.Row) -> Check:
    """E10: was this the caller's bytes, or this system's rendering of them?"""
    value = row["params_provenance"]
    if value is None:
        return Check(
            "params_provenance",
            Status.ABSENT,
            "row predates 0.4.0; provenance was not recorded and cannot be inferred",
        )
    declared = {p.value for p in Provenance}
    if value not in declared:
        return Check("params_provenance", Status.FAILED, f"{value!r} is not a declared provenance")
    return Check("params_provenance", Status.VERIFIED, value)


def _check_reason_vocabulary(row: sqlite3.Row) -> Check:
    """The reason code is one this PDP can emit, under the protocol the row claims --
    OR one it used to be able to emit, under the protocol the row's OWN stamp proves
    it was written under.

    A code live in the CURRENT build's vocabulary is `verified`. A retired code is
    not automatically `failed`: an operator who upgrades must not see every historical
    budget denial turn into a failed verification, because those rows were correct
    when written -- a product about honest records cannot show an honest record as
    failed. So a retired code gets `retired_vocabulary` exactly when the row's own
    `protocol` column proves it predates that code's retirement (`RETIRED_BEFORE`),
    and stays `failed` when the row's protocol postdates it -- the two cases differ by
    WHEN the row was written, never by the code alone, which is why the existing test
    that forces a retired code into a CURRENT row still fails here, unchanged.

    Where no row-carried marker can tell "before" from "after" a retirement --
    `cap_value`/`cap_rate`, retired without a protocol bump -- this still reads
    `failed`, deliberately unresolved rather than guessed at; see `RETIRED_BEFORE`.
    """
    reason = row["reason_code"]
    live = {c.value for c in CheckId}
    protocol = row["protocol"] or "aadp/0.1"
    if reason in live:
        return Check("reason_vocabulary", Status.VERIFIED, f"{reason} under {protocol}")
    valid_under = RETIRED_BEFORE.get(reason)
    if valid_under is not None and protocol == valid_under:
        return Check(
            "reason_vocabulary",
            Status.RETIRED_VOCABULARY,
            f"{reason} was live under {protocol}, retired since",
        )
    return Check(
        "reason_vocabulary",
        Status.FAILED,
        f"{reason!r} is not in this build's vocabulary",
    )


def _check_budget_object(row: sqlite3.Row) -> Check:
    """E7: a cap denial carries all seven budget fields, persisted and parseable."""
    raw = row["budget_json"]
    is_cap_denial = row["decision"] == "denied" and row["reason_code"] in CAP_REASONS
    if not is_cap_denial:
        if raw is not None:
            return Check(
                "budget_object",
                Status.FAILED,
                "a budget object on a verdict that is not a cap denial",
            )
        return Check("budget_object", Status.ABSENT, "not a cap denial; no budget is owed")
    if raw is None:
        return Check(
            "budget_object",
            Status.FAILED,
            f"reason {row['reason_code']} with no budget: the window cannot be named",
        )
    # A row sealed before 0.8.0 carries budget_json in the OLD shape (CAP_VALUE/
    # CAP_RATE), never rewritten into the current one -- validating it against
    # the current `Budget` model would report every pre-0.8.0 cap denial FAILED
    # the moment the shape changed under it, which is exactly the regression
    # "old rows are never rewritten" exists to prevent.
    model = LegacyBudget if row["reason_code"] in LEGACY_CAP_REASONS else Budget
    try:
        model.model_validate_json(raw)
    except ValueError as exc:
        return Check("budget_object", Status.FAILED, f"budget does not parse: {exc}")
    return Check("budget_object", Status.VERIFIED, "seven fields present and parseable")


def _check_policy_snapshot(conn: sqlite3.Connection, row: sqlite3.Row) -> Check:
    """Re-derive the policy version from the stored snapshot text.

    Two fields written at different moments -- `snapshot_json` and `version_hash` --
    so a disagreement between them is evidence rather than a tautology. This is the
    one genuine digest check `0.4.1` can offer, and it is the "same policy" half of
    the re-derivation promise the receipt footer makes.
    """
    recorded = row["policy_version"]
    if recorded is None:
        return Check("policy_snapshot", Status.ABSENT, "no policy version stamped on this row")
    found = conn.execute(
        "SELECT snapshot_json, snapshot_schema FROM policy_versions WHERE version_hash=?",
        (recorded,),
    ).fetchone()
    if found is None:
        return Check(
            "policy_snapshot",
            Status.UNVERIFIABLE,
            f"no snapshot stored for {recorded[:12]}…; the rules that produced this "
            f"verdict cannot be re-read",
        )
    snapshot = found["snapshot_json"]
    if not isinstance(snapshot, str):
        return Check("policy_snapshot", Status.FAILED, "stored snapshot is not text")
    computed = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    if computed != recorded:
        return Check(
            "policy_snapshot",
            Status.FAILED,
            f"snapshot hashes to {computed[:12]}… but the row records {recorded[:12]}…",
        )
    schema = found["snapshot_schema"] or "onedoor/policy-snapshot/1"
    return Check("policy_snapshot", Status.VERIFIED, f"re-derived under {schema}")


def _check_append_only(conn: sqlite3.Connection) -> Check:
    """The ledger's append-only claim is a claim about the STORE, not about a row."""
    names = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    }
    missing = [t for t in REQUIRED_AUDIT_TRIGGERS if t not in names]
    if missing:
        return Check(
            "append_only",
            Status.FAILED,
            f"append-only triggers missing: {', '.join(missing)}",
        )
    return Check("append_only", Status.VERIFIED, "no-update and no-delete triggers installed")


def _check_chain(row: sqlite3.Row) -> Check:
    """ND-001's hash chain. Dark in 0.4.1, and said so rather than shown green.

    All three NULL is `absent` -- a fact about the roadmap. SOME of them NULL is
    `unverifiable`, because that would be a chain that ran and did not finish, which
    is not something to reassure anyone about.
    """
    present = {c: row[c] for c in CHAIN_COLUMNS}
    filled = [c for c, v in present.items() if v is not None]
    if not filled:
        return Check(
            "chain",
            Status.ABSENT,
            "chain not yet in operation (ND-001); the columns exist and are NULL",
        )
    if len(filled) != len(CHAIN_COLUMNS):
        blank = [c for c in CHAIN_COLUMNS if c not in filled]
        return Check(
            "chain",
            Status.UNVERIFIABLE,
            f"chain is partly written: {', '.join(filled)} set, {', '.join(blank)} NULL",
        )
    # ND-001 landed: recompute this row's hash from what the store holds and compare.
    # Whether the row LINKS correctly to its neighbours is a question about the log,
    # answered by `chain.verify_chain`; this check is about the row in hand, which is
    # what a receipt is.
    recomputed = row_hash_of(row)
    if recomputed != str(present["row_hash"]):
        return Check(
            "chain",
            Status.FAILED,
            f"the row's contents hash to {recomputed[:12]}… but it records "
            f"{str(present['row_hash'])[:12]}…",
        )
    return Check("chain", Status.VERIFIED, f"seq {present['seq']}, contents re-derived")


def _check_signature(
    conn: sqlite3.Connection, row: sqlite3.Row, trusted_key_id: str | None
) -> Check:
    """Five outcomes, because `verified` needs a witness that is not the store.

    A signature checked against a public key found in the SAME STORE as the row it
    signs proves internal consistency: an attacker with write access supplies both the
    altered row and the key that vouches for it. So `verified` requires a
    `trusted_key_id` the CALLER supplies from outside — and the in-store match, which is
    real information, gets its own honest name rather than being discarded or promoted.

    **A receipt system must not be its own witness** (R038 §1).
    """
    keys = row.keys()
    signature = row["sig"] if "sig" in keys else None
    key_id = row["key_id"] if "key_id" in keys else None
    if signature is None and key_id is None:
        return Check("signature", Status.ABSENT, "signing was not in operation for this row")
    if signature is None or key_id is None:
        return Check(
            "signature",
            Status.UNVERIFIABLE,
            "a signature is half written: one of `sig`/`key_id` is set and the other "
            "is not, which is a signer that ran and did not finish",
        )

    row_hash = row["row_hash"] if "row_hash" in keys else None
    if row_hash is None:
        return Check(
            "signature",
            Status.UNVERIFIABLE,
            "the row is signed but unchained: there is no row_hash for the signature to attest",
        )

    ring = signing.keyring(conn)
    public = ring.get(str(key_id))
    if public is None:
        # R037 §2's ruled case. The signature may be perfectly good; nothing here
        # vouches for the key, and guessing either way would be inventing an answer.
        return Check(
            "signature",
            Status.UNVERIFIABLE,
            f"signed by {str(key_id)[:20]}…, a key this store has never seen",
        )

    if not signing.verify_signature(public, str(row_hash), str(signature)):
        return Check("signature", Status.FAILED, "the signature does not verify over this row")

    if trusted_key_id is None:
        return Check(
            "signature",
            Status.SELF_CONSISTENT,
            "signature matches this store's own keyring; supply a trusted key to verify",
        )
    if str(trusted_key_id) != str(key_id):
        return Check(
            "signature",
            Status.UNVERIFIABLE,
            f"signed by {str(key_id)[:20]}…, which is not the key you trusted",
        )
    return Check(
        "signature", Status.VERIFIED, f"verified against the key you supplied, {ALGORITHM}"
    )


def _check_anchor(conn: sqlite3.Connection, row: sqlite3.Row, published_root: str | None) -> Check:
    """Membership in a published Merkle tree (ND-017 / M5).

    R038 §4's law one more time: **an anchor is worth exactly the independence of where
    it lives.** A proof that checks against a root found in this store is
    `self_consistent`, and `verified` needs the root the caller obtained from outside —
    the same shape as the signature check, which is now the second place this product
    declines to vouch for itself.

    `absent` matters more here than anywhere else: **anchoring is periodic by design**,
    so the newest rows are always un-anchored, and a viewer that showed them red would
    train an operator to ignore red.
    """
    from onedoor.guardrail import anchoring

    keys = row.keys()
    if "seq" not in keys or row["seq"] is None:
        return Check("anchor", Status.ABSENT, "unchained rows are not anchored")
    try:
        export = anchoring.receipt_export(conn, row)
    except anchoring.AnchorError as exc:
        return Check("anchor", Status.UNVERIFIABLE, str(exc))
    outcome, detail = anchoring.check_membership(export, published_root)
    status = {
        anchoring.MEMBERSHIP_VERIFIED: Status.VERIFIED,
        anchoring.MEMBERSHIP_SELF_CONSISTENT: Status.SELF_CONSISTENT,
        anchoring.MEMBERSHIP_ABSENT: Status.ABSENT,
        anchoring.MEMBERSHIP_UNVERIFIABLE: Status.UNVERIFIABLE,
        anchoring.MEMBERSHIP_FAILED: Status.FAILED,
    }[outcome]
    return Check("anchor", status, detail)


def verify_decision(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    trusted_key_id: str | None = None,
    published_root: str | None = None,
) -> ReceiptVerification:
    """Verify one audit row. THE implementation; callers render its output.

    Ordered deliberately: byte-form checks run before anything hashes (R028), and the
    store-level check runs last because it is about the ledger rather than the row.
    """
    return ReceiptVerification(
        checks=(
            _check_params_byte_form(row),
            _check_params_provenance(row),
            _check_reason_vocabulary(row),
            _check_budget_object(row),
            _check_policy_snapshot(conn, row),
            _check_chain(row),
            _check_signature(conn, row, trusted_key_id),
            _check_anchor(conn, row, published_root),
            _check_append_only(conn),
        )
    )


def fetch_decision(conn: sqlite3.Connection, audit_id: int) -> sqlite3.Row | None:
    """One audit row by id, or None. Kept here so callers share one query shape."""
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM actions_audit WHERE id=?", (audit_id,)
    ).fetchone()
    return row


VERDICT_KINDS = ("decision", "exec_intent")
"""The audit kinds that ARE a verdict, as opposed to a follow-up to one.

Worth spelling out, because the obvious reading is wrong and it took a failing test
to notice. `kind='decision'` is written for a denial, a proposal, an observation and a
dry-run -- every terminal verdict EXCEPT a permit. A permitted action writes
`kind='exec_intent'`, because at that moment the engine's answer is an obligation on
the caller rather than a closed outcome.

A tail filtered to `decision` alone would therefore show denials and nothing else, and
would read as a machine that only ever refuses. That is not a cosmetic problem: the
whole claim of this product is that the record is faithful, and a feed that
systematically omits every approval is not faithful. `exec_result` and
`reservation_released` stay out -- those report what happened AFTER a verdict, and
belong to a receipt rather than being one.
"""


def latest_verdicts(conn: sqlite3.Connection, limit: int = 12) -> list[sqlite3.Row]:
    """The most recent verdict rows, newest first — the live tail's contents."""
    placeholders = ",".join("?" for _ in VERDICT_KINDS)
    return list(
        conn.execute(
            f"SELECT * FROM actions_audit WHERE kind IN ({placeholders}) "  # noqa: S608
            f"ORDER BY id DESC LIMIT ?",
            (*VERDICT_KINDS, limit),
        ).fetchall()
    )


def hero_decision(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The receipt worth putting at the top: the most recent cap denial with a budget.

    The spec names deny-with-budget as the demo hero because it is the verdict that
    carries the most evidence -- a typed reason, a seven-field budget, a named effect.
    Falls back to the most recent decision of any kind, and to None on an empty store,
    because a viewer that requires a particular verdict to exist is a viewer that
    cannot be pointed at a real system on its first day.
    """
    placeholders = ",".join("?" for _ in CAP_REASONS)
    row: sqlite3.Row | None = conn.execute(
        f"SELECT * FROM actions_audit WHERE kind='decision' AND decision='denied' "  # noqa: S608
        f"AND reason_code IN ({placeholders}) AND budget_json IS NOT NULL "
        f"ORDER BY id DESC LIMIT 1",
        tuple(sorted(CAP_REASONS)),
    ).fetchone()
    if row is not None:
        return row
    kinds = ",".join("?" for _ in VERDICT_KINDS)
    fallback: sqlite3.Row | None = conn.execute(
        f"SELECT * FROM actions_audit WHERE kind IN ({kinds}) ORDER BY id DESC LIMIT 1",  # noqa: S608
        VERDICT_KINDS,
    ).fetchone()
    return fallback
