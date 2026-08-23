"""The four digests, against a second implementation and six golden vectors (M1).

`_from_the_document` is built from `docs/receipt-digests.md` §§2–5, not from
`onedoor/guardrail/digests.py`. An implementation that agrees with itself has proved
nothing — the P2-06 pattern `test_row_preimage.py` already carries, applied to the
second frozen definition in this epic.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor._vendor.canonical import canonical_bytes, digest_obj
from onedoor.guardrail import chain, digests, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

SPEC = Path(__file__).resolve().parents[2] / "docs" / "receipt-digests.md"


# --- The second implementation, from the document --------------------------------


def _doc_fields(section: str) -> list[str]:
    """The field names the document declares for one object, read from its own fence."""
    text = SPEC.read_text(encoding="utf-8")
    body = text.split(section, 1)[1].split("```", 2)[1]
    return re.findall(r'"([a-z_]+)"\s*:', body)


def _from_the_document(obj: dict[str, object]) -> str:
    """Digest by following §1 literally: SHA-256 over canonical JSON, nothing else.

    Written a different way from the module: an explicit sort and join rather than the
    vendored helper, so the two agree on the encoding and not merely on a shared call.
    """

    def render(value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, list):
            return "[" + ",".join(render(v) for v in value) + "]"
        if isinstance(value, dict):
            inner = ",".join(
                f"{json.dumps(k, ensure_ascii=False)}:{render(v)}" for k, v in sorted(value.items())
            )
            return "{" + inner + "}"
        raise TypeError(type(value).__name__)

    return hashlib.sha256(render(obj).encode("utf-8")).hexdigest()


def _seeded(conn: Connection, config: EngineConfig) -> Connection:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("10")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    with tx(conn):
        chain.enable(conn)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("99")}, cost_eur=Decimal("99")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    return conn


def _row(conn: Connection):  # type: ignore[no-untyped-def]
    return conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()


# --- The document is a definition --------------------------------------------------


def test_the_document_and_the_module_declare_the_same_fields(
    conn: Connection, config: EngineConfig
) -> None:
    row = _row(_seeded(conn, config))
    for section, built in (
        ("## 2. `E`", digests.evidence(row)),
        ("## 3. `I`", digests.instrument(row)),
        ("## 5. `v`", digests.verdict(row)),
    ):
        assert _doc_fields(section) == list(built), (
            f"{section} and the module disagree on fields or order. The document is "
            f"normative; these digests freeze on the first sealed row."
        )
    assert _doc_fields("## 4. `T`") == list(digests.trust(row, closure=digests.STORE_CLOSED))


def test_the_second_implementation_agrees(conn: Connection, config: EngineConfig) -> None:
    row = _row(_seeded(conn, config))
    for obj in (
        digests.evidence(row),
        digests.instrument(row),
        digests.trust(row, closure=digests.STORE_CLOSED),
        digests.verdict(row),
    ):
        assert _from_the_document(obj) == digest_obj(obj)


# --- The six golden vectors --------------------------------------------------------


def test_vector_the_empty_trust_set_matches_the_vendored_artifact() -> None:
    """The arithmetic that proved the reading rather than the reading proving itself.

    The shipped manifests in `reference/rederivable-manifest/manifests/` carry
    `t_digest = 4f53cda1…b945`, and that is SHA-256 of canonical `[]`. Computing it is
    how the decomposition established that `T` is a *declared closure* rather than a bag
    of facts — which is also what made R040's amendment (drop `policy_source`) land as a
    correction rather than a preference.
    """
    assert digest_obj([]) == "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    assert _from_the_document({}) == digest_obj({})


def test_vector_key_order_is_erased() -> None:
    assert digest_obj({"b": 1, "a": "x"}) == digest_obj({"a": "x", "b": 1})
    assert canonical_bytes({"b": 1, "a": "x"}) == b'{"a":"x","b":1}'


def test_vector_absent_is_not_empty() -> None:
    """R015 at the digest layer: `null` and `""` are different facts."""
    for field in ("params_provenance", "policy_version", "snapshot_schema"):
        base = {"kind": digests.EVIDENCE_KIND, field: None}
        empty = {"kind": digests.EVIDENCE_KIND, field: ""}
        assert digest_obj(base) != digest_obj(empty), f"{field}: null collapsed into empty"


def test_vector_one_byte_perturbation(conn: Connection, config: EngineConfig) -> None:
    row = _row(_seeded(conn, config))
    for build in (digests.evidence, digests.verdict):
        obj = build(row)
        baseline = digest_obj(obj)
        for key, value in obj.items():
            if not isinstance(value, str) or not value:
                continue
            moved = dict(obj)
            moved[key] = value[:-1] + chr(ord(value[-1]) ^ 1)
            assert digest_obj(moved) != baseline, f"a one-byte change in {key} did not move it"


def test_vector_policy_version_is_in_evidence_and_not_in_trust(
    conn: Connection, config: EngineConfig
) -> None:
    """R040 §1's amendment, asserted so it cannot be quietly undone.

    The policy hash is an INPUT IDENTITY and `E` seals it. Carrying it in `T` as well
    would be two answers to one question at the exact layer where drift becomes
    undetectable — X-14, inside the seal itself.
    """
    row = _row(_seeded(conn, config))
    assert "policy_version" in digests.evidence(row)
    trust = digests.trust(row, closure=digests.STORE_CLOSED)
    assert set(trust) == {"kind", "keys", "closure"}, (
        f"T must be a statement of what must be trusted, never a second copy of facts "
        f"E already seals: {sorted(trust)}"
    )
    assert "policy_source" not in trust
    assert "policy_version" not in trust


def test_vector_the_instrument_carries_no_cadence(conn: Connection, config: EngineConfig) -> None:
    """R040 §2's amendment, and the reason it was a defect rather than a choice.

    Cadence schedules anchoring, not deciding. Inside `I`, an ops-schedule tweak would
    re-identify the DECIDING instrument for every row after it — splitting `i_digest`
    cohorts for a reason no instrument comparison should have to care about.
    """
    row = _row(_seeded(conn, config))
    inst = digests.instrument(row)
    assert not any("cadence" in k for k in inst), f"cadence leaked into I: {sorted(inst)}"
    assert SPEC.read_text(encoding="utf-8").count("anchor_cadence") >= 1, (
        "the document must still explain WHY it is absent, or the next reader adds it back"
    )


# --- Shape and behaviour -----------------------------------------------------------


def test_the_params_digest_is_over_the_frozen_bytes_verbatim(
    conn: Connection, config: EngineConfig
) -> None:
    """E10, and the privacy property in the same move.

    A receipt can be handed to a third party without handing over the request body,
    because the body never enters the digest structure — only its hash does.
    """
    row = _row(_seeded(conn, config))
    stored = row["params_json"]
    raw = stored.encode("utf-8") if isinstance(stored, str) else bytes(stored)
    evidence = digests.evidence(row)
    assert evidence["params_digest"] == hashlib.sha256(raw).hexdigest()
    assert stored not in json.dumps(evidence), "the request body must not be inlined"


def test_the_budget_is_carried_as_its_stored_text(conn: Connection, config: EngineConfig) -> None:
    """Re-rendering would let the sealed bytes and the stored bytes diverge."""
    row = _row(_seeded(conn, config))
    assert row["budget_json"] is not None, "the fixture must be a cap denial"
    assert digests.verdict(row)["budget"] == row["budget_json"]


def test_all_four_digests_are_lowercase_hex(conn: Connection, config: EngineConfig) -> None:
    row = _row(_seeded(conn, config))
    for name, value in digests.digests_for(row).items():
        assert re.fullmatch(r"[0-9a-f]{64}", value), f"{name} is not a lowercase hex sha256"


def test_two_different_rows_do_not_share_a_verdict_digest(
    conn: Connection, config: EngineConfig
) -> None:
    _seeded(conn, config)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("1")}, cost_eur=Decimal("1")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    rows = conn.execute("SELECT * FROM actions_audit ORDER BY id").fetchall()
    seen = {digest_obj(digests.verdict(r)) for r in rows}
    assert len(seen) > 1, "distinct verdicts must not share a v_digest"


def test_the_closure_is_a_declaration_with_exactly_two_values(
    conn: Connection, config: EngineConfig
) -> None:
    row = _row(_seeded(conn, config))
    store = digests.trust(row, closure=digests.STORE_CLOSED)
    anchor = digests.trust(row, closure=digests.ANCHOR_CLOSED)
    assert store["closure"] == "store-closed"
    assert anchor["closure"] == "anchor-closed"
    assert digest_obj(store) != digest_obj(anchor), (
        "the closure declaration must change the trust digest; it is the whole content"
    )


def test_a_float_cannot_enter_a_digest() -> None:
    """The vendored canonicaliser forbids floats outright, and that is load-bearing."""
    with pytest.raises(TypeError, match="floats are forbidden"):
        digest_obj({"kind": digests.VERDICT_KIND, "amount": 1.5})
