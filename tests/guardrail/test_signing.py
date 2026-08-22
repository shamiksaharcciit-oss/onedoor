"""Signed receipts, and the five outcomes that keep them honest (ND-015, K1–K5).

The test this file is really about is
`test_a_store_never_reports_verified_on_its_own`. Everything else is scaffolding for
it.

**A receipt system must not be its own witness** (R038 §1). A signature checked against
a public key found in the same store as the row it signs proves internal consistency:
an attacker with write access supplies both the altered row and the key that vouches
for it. So the in-store match is `self_consistent` — named, real, and not verification
— and `verified` requires a trusted `key_id` the caller brings from outside.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader, signing
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.guardrail.receipt import Status, verify_decision
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _keyfile(tmp_path: Path, name: str = "signing") -> Path:
    """A deployer-supplied private key. Generated here; never in the repo or the DB."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    path = tmp_path / f"{name}.pem"
    path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return path


def _policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )


def _decide(conn: Connection, config: EngineConfig) -> None:
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)


def _signed_store(conn: Connection, config: EngineConfig, tmp_path: Path) -> str:
    _policy(conn)
    with tx(conn):
        chain.enable(conn, signing_key_path=str(_keyfile(tmp_path)))
    _decide(conn, config)
    return str(
        conn.execute("SELECT key_id FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()[
            "key_id"
        ]
    )


def _latest(conn: Connection):  # type: ignore[no-untyped-def]
    return conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()


# --- The ruling this ticket exists for -------------------------------------------


def test_a_store_never_reports_verified_on_its_own(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """R038 §1. The in-store match is real, named, and not verification.

    Most systems would call this verified. That is exactly the instinct the rule
    refuses: an attacker who can write the database adds their own public key,
    re-signs what they altered, and the store agrees with itself perfectly.
    """
    key_id = _signed_store(conn, config, tmp_path)
    check = verify_decision(conn, _latest(conn)).by_name("signature")
    assert check.status is Status.SELF_CONSISTENT
    assert "supply a trusted key" in check.detail

    with_anchor = verify_decision(conn, _latest(conn), trusted_key_id=key_id).by_name("signature")
    assert with_anchor.status is Status.VERIFIED, (
        "a caller-supplied trust anchor is what turns a self-consistent match into a verification"
    )


def test_self_consistent_is_neither_a_fault_nor_a_pass(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """It must not block the receipt, and it must not read as a tick."""
    _signed_store(conn, config, tmp_path)
    verification = verify_decision(conn, _latest(conn))
    check = verification.by_name("signature")
    assert not check.is_fault, "a self-consistent signature is not damage"
    assert check.is_partial, "and it is not a pass either"
    assert verification.sound


def test_a_trusted_key_that_is_not_this_one_is_unverifiable(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """Anchoring to the wrong key is not a failure of the signature."""
    _signed_store(conn, config, tmp_path)
    other = signing.load_private_key(str(_keyfile(tmp_path, "other")))
    check = verify_decision(conn, _latest(conn), trusted_key_id=other.key_id).by_name("signature")
    assert check.status is Status.UNVERIFIABLE
    assert "not the key you trusted" in check.detail


# --- The other four outcomes -----------------------------------------------------


def test_an_unsigned_row_is_absent_not_a_failure(conn: Connection, config: EngineConfig) -> None:
    """Signing was not in operation — the same word as the chain before ND-001."""
    _policy(conn)
    _decide(conn, config)
    check = verify_decision(conn, _latest(conn)).by_name("signature")
    assert check.status is Status.ABSENT
    assert verify_decision(conn, _latest(conn)).sound


def test_an_unknown_key_is_unverifiable_never_failed(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """R037 §2's ruled case: the signature may be perfectly good."""
    _signed_store(conn, config, tmp_path)
    with tx(conn):
        conn.execute("DROP TRIGGER signing_keys_no_delete")
        conn.execute("DELETE FROM signing_keys")
    check = verify_decision(conn, _latest(conn)).by_name("signature")
    assert check.status is Status.UNVERIFIABLE
    assert "never seen" in check.detail


def test_a_bad_signature_fails(conn: Connection, config: EngineConfig, tmp_path: Path) -> None:
    _signed_store(conn, config, tmp_path)
    row = _latest(conn)
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute("UPDATE actions_audit SET sig=? WHERE id=?", ("00" * 64, int(row["id"])))
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )
    check = verify_decision(conn, _latest(conn)).by_name("signature")
    assert check.status is Status.FAILED


def test_a_half_written_signature_is_unverifiable(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """A signer that ran and did not finish is a different fact from one that never ran."""
    _signed_store(conn, config, tmp_path)
    row = _latest(conn)
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute("UPDATE actions_audit SET sig=NULL WHERE id=?", (int(row["id"]),))
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )
    check = verify_decision(conn, _latest(conn)).by_name("signature")
    assert check.status is Status.UNVERIFIABLE
    assert "half written" in check.detail


# --- K5: the adversarial set ------------------------------------------------------


def test_a_signature_cannot_be_lifted_from_one_row_onto_another(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """The signed bytes are the row's own hash, so a stolen signature does not travel.

    Without `row_hash` in the signed message this would pass — which is why signing is
    per-row over `row_hash` rather than over a constant or a request id.
    """
    _signed_store(conn, config, tmp_path)
    _decide(conn, config)
    first, second = conn.execute(
        "SELECT * FROM actions_audit WHERE sig IS NOT NULL ORDER BY id"
    ).fetchall()[:2]
    assert first["sig"] != second["sig"], "two rows must not share a signature"

    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute("UPDATE actions_audit SET sig=? WHERE id=?", (first["sig"], int(second["id"])))
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )
    moved = conn.execute("SELECT * FROM actions_audit WHERE id=?", (int(second["id"]),)).fetchone()
    assert verify_decision(conn, moved).by_name("signature").status is Status.FAILED


def test_a_substituted_public_key_cannot_be_added_over_the_real_one(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """The keyring is append-only: a rotated-out key cannot be quietly removed.

    This does NOT close the trust hole — an attacker can still ADD a key, which is
    precisely why an in-store match is `self_consistent` rather than `verified`. What it
    closes is the other half: a key whose receipts still exist cannot be deleted to make
    them unverifiable.
    """
    import sqlite3 as sq

    key_id = _signed_store(conn, config, tmp_path)
    with pytest.raises(sq.IntegrityError), tx(conn):
        conn.execute("DELETE FROM signing_keys WHERE key_id=?", (key_id,))
    with pytest.raises(sq.IntegrityError), tx(conn):
        conn.execute("UPDATE signing_keys SET public_key=? WHERE key_id=?", (b"x" * 32, key_id))


def test_an_attacker_who_adds_a_key_still_cannot_reach_verified(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """The whole argument, demonstrated rather than asserted.

    The attacker re-signs a row they altered with their own key and registers it. The
    store agrees with itself — `self_consistent` — and the caller's trust anchor still
    refuses it. That gap is the product.
    """
    trusted = _signed_store(conn, config, tmp_path)
    attacker = signing.load_private_key(str(_keyfile(tmp_path, "attacker")))
    row = _latest(conn)

    with tx(conn):
        signing.register_public_key(
            conn, signing.public_bytes_of(attacker), FROZEN_NOW, note="planted"
        )
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute(
            "UPDATE actions_audit SET sig=?, key_id=? WHERE id=?",
            (attacker.sign(str(row["row_hash"])), attacker.key_id, int(row["id"])),
        )
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )

    forged = _latest(conn)
    assert verify_decision(conn, forged).by_name("signature").status is Status.SELF_CONSISTENT, (
        "the store agrees with itself, which is exactly why that word is not `verified`"
    )
    anchored = verify_decision(conn, forged, trusted_key_id=trusted).by_name("signature")
    assert anchored.status is Status.UNVERIFIABLE, (
        "an external trust anchor refuses the planted key — the gap this design exists for"
    )


# --- K4: rotation -----------------------------------------------------------------


def test_rotation_grows_the_keyring_and_old_receipts_still_verify(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """Public keys are evidence, and evidence is not deleted."""
    first_key_id = _signed_store(conn, config, tmp_path)
    old_row = _latest(conn)

    second = signing.load_private_key(str(_keyfile(tmp_path, "rotated")))
    with tx(conn):
        signing.register_public_key(
            conn, signing.public_bytes_of(second), FROZEN_NOW, note="rotation"
        )
    assert len(signing.keyring(conn)) == 2, "rotation grows the ring; it does not replace"

    assert (
        verify_decision(conn, old_row, trusted_key_id=first_key_id).by_name("signature").status
        is Status.VERIFIED
    ), "a receipt signed by a rotated-out key must verify forever"


def test_registering_the_same_key_twice_is_one_fact(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    _signed_store(conn, config, tmp_path)
    key = signing.load_private_key(str(_keyfile(tmp_path, "again")))
    with tx(conn):
        first = signing.register_public_key(conn, signing.public_bytes_of(key), FROZEN_NOW)
        second = signing.register_public_key(conn, signing.public_bytes_of(key), FROZEN_NOW)
    assert first == second
    assert len(signing.keyring(conn)) == 2


# --- Custody and identity ---------------------------------------------------------


def test_no_private_key_material_reaches_the_store(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """R037 §2, checked against the bytes rather than trusted.

    The config records a PATH; the keyring records a PUBLIC key; the row records a
    derived id and a signature. A private key appears nowhere.
    """
    path = _keyfile(tmp_path, "custody")
    private_pem = path.read_bytes()
    _policy(conn)
    with tx(conn):
        chain.enable(conn, signing_key_path=str(path))
    _decide(conn, config)

    dump = "\n".join(
        str(v)
        for table in ("config", "signing_keys", "actions_audit")
        for row in conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
        for v in tuple(row)
    ).encode("utf-8", "replace")
    assert b"PRIVATE KEY" not in dump
    assert private_pem.strip() not in dump


def test_the_key_id_is_derived_not_assigned(tmp_path: Path) -> None:
    """A chosen label can drift from what it names; a fingerprint cannot."""
    key = signing.load_private_key(str(_keyfile(tmp_path, "derived")))
    public = signing.public_bytes_of(key)
    assert key.key_id == signing.key_id_for(public)
    assert key.key_id.startswith("ed25519:")
    assert len(key.key_id) == len("ed25519:") + 64

    other = signing.load_private_key(str(_keyfile(tmp_path, "derived2")))
    assert other.key_id != key.key_id


def test_alg_records_the_algorithm_and_not_the_library(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """R038 §3. Ed25519 is deterministic per RFC 8032, so a library version in per-row
    evidence would assert an output dependence that does not exist — and a misleading
    identity in a receipt is worse than none."""
    _signed_store(conn, config, tmp_path)
    row = _latest(conn)
    assert row["alg"] == "ed25519"
    import cryptography

    assert cryptography.__version__ not in str(row["alg"])


# --- X-6 at enable time -----------------------------------------------------------


def test_signing_configured_with_the_library_missing_refuses_to_start(
    conn: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R038 §2, as a stated invariant rather than an emergent property.

    A hard install dependency would not have cured this: belief comes from config. The
    cure is refusing loudly at the moment the alarm becomes real, so there is never a
    stream of unsigned rows in a deployment that thinks it signs.
    """
    import builtins

    real_import = builtins.__import__

    def no_crypto(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("cryptography"):
            raise ImportError("no cryptography in this deployment")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", no_crypto)
    assert not signing.available()
    with (
        pytest.raises(signing.SigningUnavailable, match="refusing to start|Refusing to start"),
        tx(conn),
    ):
        chain.enable(conn, signing_key_path=str(tmp_path / "never-read.pem"))


def test_an_unreadable_key_stops_the_enable_rather_than_half_enabling(
    conn: Connection, tmp_path: Path
) -> None:
    """A store that thinks it signs and has no key is the failure mode, not the error."""
    with pytest.raises(signing.SigningUnavailable, match="unreadable"), tx(conn):
        chain.enable(conn, signing_key_path=str(tmp_path / "absent.pem"))
    assert not chain.enabled(conn), "a failed enable must leave chaining off"


def test_chaining_without_signing_still_works(conn: Connection, config: EngineConfig) -> None:
    """Signing rides chaining; it is not required by it."""
    _policy(conn)
    with tx(conn):
        chain.enable(conn)
    _decide(conn, config)
    row = _latest(conn)
    assert row["row_hash"] is not None
    assert row["sig"] is None
    assert verify_decision(conn, row).by_name("signature").status is Status.ABSENT


def test_the_signature_survives_a_cap_denial_row(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """Every appended row is signed, not just permits."""
    from onedoor.guardrail.models import Caps

    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("1")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    with tx(conn):
        chain.enable(conn, signing_key_path=str(_keyfile(tmp_path, "denials")))
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("99")}, cost_eur=Decimal("99")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    row = _latest(conn)
    assert row["reason_code"] == "cap_value"
    assert row["sig"] is not None
    assert verify_decision(conn, row).by_name("signature").status is Status.SELF_CONSISTENT
