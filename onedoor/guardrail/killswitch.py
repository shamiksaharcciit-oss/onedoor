"""Global kill switch — a single flag in the ``config`` table.

The executor reads this FIRST, before any policy lookup (invariant: kill switch
check is first). When engaged, every acting tier is clamped to propose-only.
M1 will mirror this flag to a Home Assistant ``input_boolean``; the executor keeps
reading exactly one source of truth here regardless.

What the switch does *not* stop, and what follows from that (R045 §5)
----------------------------------------------------------------------
It does not stop **policy-making**. That is not an omission; it is a consequence of
how completely it stops everything else. Nothing ratified can move while the switch
holds, so a mid-incident ratification cannot cause an effect — and blocking it would
punish the operator tightening rules during an incident while stopping no attacker who
already had ratification access.

**The moment of risk is the lift.** So the switch records the policy version in force
when it was engaged, and the release path reports any change since: *"the rules changed
while the door was shut, from X to Y."* The report is surfaced and recorded; the lift
is not blocked either. This product makes states visible; it does not take the wheel.

The law, for the file: *the switch that stops everything need not stop the pen — it
already stops the consequences, and the lift is where the pen's work must be shown.*
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from onedoor.guardrail import policy_loader
from onedoor.store.clock import now_utc, to_iso

_KEY = "kill_switch_engaged"

NO_EPISODE = "no_episode"
UNCHANGED = "unchanged"
CHANGED = "changed"
UNDETERMINABLE = "undeterminable"
"""Four states, and none of them collapses into another (R010).

`NO_EPISODE` — nothing was recorded for this engagement, so there is no comparison to
make. A store upgraded while the switch was already held has this, and it is **not** a
statement that the rules held still.

`UNDETERMINABLE` — an episode exists but recorded no version, because the store had
none. Also not a statement that the rules held still.

Only `UNCHANGED` says the rules held still, and it says it because two hashes were
compared and matched.
"""


@dataclass(frozen=True)
class LiftReport:
    """What the human lifting the switch is told before the door opens."""

    state: str
    version_at_engagement: str | None
    version_at_release: str | None
    engaged_at: str | None

    @property
    def is_a_change(self) -> bool:
        return self.state == CHANGED

    def to_object(self) -> dict[str, object]:
        return {
            "state": self.state,
            "version_at_engagement": self.version_at_engagement,
            "version_at_release": self.version_at_release,
            "engaged_at": self.engaged_at,
        }

    def sentence(self) -> str:
        """One line, for a UI or a log. Says which of the four states it is."""
        if self.state == CHANGED:
            return (
                f"The rules changed while the door was shut, from "
                f"{_short(self.version_at_engagement)} to {_short(self.version_at_release)}."
            )
        if self.state == UNCHANGED:
            return "The rules did not change while the door was shut."
        if self.state == UNDETERMINABLE:
            return (
                "Whether the rules changed while the door was shut cannot be determined: "
                "no policy version was recorded when the switch was engaged."
            )
        return (
            "No engagement was recorded for this switch, so whether the rules changed "
            "while the door was shut is not known — this is not a report that they did not."
        )


def _short(version: str | None) -> str:
    return "no recorded version" if version is None else f"{version[:12]}..."


def is_engaged(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM config WHERE key=?", (_KEY,)).fetchone()
    return bool(row and row["value"] == "1")


def open_episode(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The engagement currently in force, or None. At most one is ever open."""
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM kill_switch_episodes WHERE released_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row


def set_engaged(
    conn: sqlite3.Connection, engaged: bool, *, origin: str = "ui"
) -> LiftReport | None:
    """Set the flag. ``origin`` (ui/ha) is recorded for provenance.

    Returns a `LiftReport` when this call **releases** the switch, and None when it
    engages one. The report is the whole of R045 §5's second requirement: the lift is
    where a policy change made behind a shut door has to become visible.
    """
    was_engaged = is_engaged(conn)
    stamp = to_iso(now_utc())
    conn.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (_KEY, "1" if engaged else "0", stamp),
    )
    conn.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ("kill_switch_origin", origin, stamp),
    )
    if engaged:
        _open(conn, stamp, origin)
        return None
    return _close(conn, stamp, was_engaged)


def _open(conn: sqlite3.Connection, stamp: str, origin: str) -> None:
    """Start an episode, unless one is already open.

    Re-engaging an engaged switch keeps the FIRST engagement's version, because the door
    has been shut since then and that is the moment the comparison must run from. An
    idempotent call that quietly reset the baseline would erase exactly the change the
    report exists to surface.
    """
    if open_episode(conn) is not None:
        return
    conn.execute(
        "INSERT INTO kill_switch_episodes (engaged_at, origin, version_hash_at_engagement) "
        "VALUES (?,?,?)",
        (stamp, origin, policy_loader.current_version(conn)),
    )


def _close(conn: sqlite3.Connection, stamp: str, was_engaged: bool) -> LiftReport | None:
    """Close the open episode and report. None when the switch was already released.

    Releasing an already-released switch is a no-op, not an occasion for a report:
    there was no door to open, and manufacturing a reassuring sentence for it would be
    the reassurance-without-evidence this system exists to avoid.
    """
    episode = open_episode(conn)
    if episode is None:
        return None if not was_engaged else _no_episode_report(conn)
    at_release = policy_loader.current_version(conn)
    at_engagement = episode["version_hash_at_engagement"]
    conn.execute(
        "UPDATE kill_switch_episodes SET released_at=?, version_hash_at_release=? WHERE id=?",
        (stamp, at_release, episode["id"]),
    )
    if at_engagement is None:
        state = UNDETERMINABLE
    elif at_engagement == at_release:
        state = UNCHANGED
    else:
        state = CHANGED
    return LiftReport(
        state=state,
        version_at_engagement=at_engagement,
        version_at_release=at_release,
        engaged_at=str(episode["engaged_at"]),
    )


def _no_episode_report(conn: sqlite3.Connection) -> LiftReport:
    """The switch was held, but nothing recorded the engagement.

    A store upgraded while the switch was already engaged lands here. It is reported as
    its own state rather than as `unchanged`, because "we have no record of when this
    door shut" and "the rules held still" are different facts and only one of them is
    reassuring.
    """
    return LiftReport(
        state=NO_EPISODE,
        version_at_engagement=None,
        version_at_release=policy_loader.current_version(conn),
        engaged_at=None,
    )
