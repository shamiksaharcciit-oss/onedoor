"""The policy proposer (ND-052 / S6, T1–T3).

**The proposer is never the enforcer.** This module drafts a *candidate*; it has no path
to the active set except `studio.ratify.ratify` — preview equality, compare-and-swap,
receipt — and its output enters that ceremony as a candidate like any other,
`candidate_digest` and all. `tests/studio/test_proposer_isolation.py` holds the other
half of that structurally: nothing the engine consults while deciding may import this
module, or reach a network client at all.

**Nothing here relies on the model refusing.** A description crafted to talk a model into
a permissive rule is an obvious attack, and the candidate passes the same validator, the
same law tests, the same coverage map and the same human ratification as a hand-written
one. Fail-closed defaults mean a rule the model got wrong is a rule that **refuses**.
That is the whole reason the proposer was built last and the ceremony first.

A record, not a receipt (R053 §1)
-----------------------------------
Every other artifact this product emits is **recomputable** — a backtest replays, a
ratification's hash is reproduced by `record_snapshot`, a coverage map is a pure function
of two addressed inputs. **A proposal is none of these**: the same description through the
same model twice may differ, and recording the instrument pins the *conditions*, never the
output.

So this emits a `DerivationRecord`, and principle 5 was **amended rather than stretched**
to make room for it — *every derivation gets a record; a record that promises re-derivation
is a receipt; a record that cannot promise it says so on its face.* The face statements are
`NOT_REDERIVABLE` and `AUTHORITY_FROM_CHECKS` below, and both travel to every rendering.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from onedoor._vendor.canonical import digest_obj
from onedoor.guardrail.models import EffectPolicy, Policy
from onedoor.store.clock import to_iso

SCHEMA = "onedoor/derivation-record/1"

LIVE = "live"
FIXTURE = "fixture"
"""`proposer_provenance`, and it is **the same value pair as `ledger_provenance`** (R053 §2).

The label's job is identical — was this the real instrument or the shipped stand-in — and
a renderer that already speaks `live | fixture` must not learn a second dialect for one
distinction. *Which* model is the instrument block's job, never the label's.
"""

NOT_REDERIVABLE = (
    "This record attests what was produced, from what, by what instrument. It does NOT "
    "attest that the same inputs would produce it again: a model is not a function, and "
    "recording the instrument pins the conditions, never the output."
)

AUTHORITY_FROM_CHECKS = (
    "The candidate's authority comes from the checks it passes, never from this record. "
    "A derivation record confers provenance, not trust."
)

FACE = (NOT_REDERIVABLE, AUTHORITY_FROM_CHECKS)
"""Both sentences, on every rendering. One constant, because two copies of a sentence are
two names for one fact."""


class ProposerUnavailable(RuntimeError):
    """A proposer was asked for and cannot be supplied. The message names the remedy."""


class ProposalRefused(RuntimeError):
    """A generation did not survive the parser. Carries the staged result and the raw text.

    Lives here, beside the `Proposer` protocol, rather than with any one implementation:
    **any** proposer can produce output the loader refuses, and a caller that wants to
    handle that — the benchmark, most importantly — must be able to catch it without
    importing a particular implementation.

    That is not tidiness. `benchmark` scores *any* instrument, and a dependency from it to
    the model-backed proposer would tie the benchmark to a track that may slip to a later
    release. The exception belongs to the protocol because the condition does.

    **The two failures are kept apart.** This one says the model answered and the answer
    was not a policy document; `ProposerUnavailable` says nothing answered. Scoring the
    second as a miss would blame the instrument for the network.
    """

    def __init__(self, message: str, result: Any, text: str) -> None:
        super().__init__(message)
        self.result = result
        """The `staging.StagedResult` — which stage refused, and why."""

        self.text = text
        """What the model actually returned, verbatim and unrepaired."""


@dataclass(frozen=True)
class Mention:
    """Something the description referred to, as **a model's reading of a sentence**.

    Not a measurement. `coverage.build`'s rows are facts about the engine and the ledger;
    this is a claim about what someone meant, and R053 §3 keeps the two in different
    sections of one surface precisely so a claim can never occupy a measurement's row.
    """

    subject: str
    kind: str
    quote: str
    covered_by: str | None = None

    def to_object(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "kind": self.kind,
            "quote": self.quote,
            "covered_by": self.covered_by,
        }


@dataclass(frozen=True)
class Proposal:
    """A drafted candidate, plus what the proposer says the description mentioned."""

    policies: list[Policy]
    effects: list[EffectPolicy] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)

    def policy_digest(self) -> str:
        """Cited, never re-minted: S1's function, called."""
        from onedoor.studio import backtest

        return backtest.policy_digest(self.policies)


@runtime_checkable
class Proposer(Protocol):
    """What the Studio needs from anything that drafts policy.

    Two members, and `identity` is not optional: **the instrument block is never empty in
    either case** (R053 §2). A fixture records its own identity, version and digest exactly
    as a model records its id — an unrecorded instrument is an unrecorded derivation.
    """

    provenance: str

    def identity(self) -> dict[str, Any]: ...

    def propose(self, description: str) -> Proposal: ...


def _prompt_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DerivationRecord:
    """What was produced, from what, by what instrument — and what it does not claim."""

    description_digest: str
    instrument: dict[str, Any]
    proposer_provenance: str
    policy_digest: str
    produced_at: str
    mentions: list[Mention] = field(default_factory=list)

    def to_object(self) -> dict[str, Any]:
        """The canonical body, with `record_digest` absent — the manifest pattern."""
        return {
            "schema": SCHEMA,
            "description_digest": self.description_digest,
            "instrument": self.instrument,
            # Inside the digest, exactly as `ledger_provenance` is inside a backtest
            # receipt's: relabelling a fixture-drafted candidate as a model's work breaks
            # this record's own address, so the label is defended by arithmetic rather
            # than by a reviewer noticing.
            "proposer_provenance": self.proposer_provenance,
            "policy_digest": self.policy_digest,
            "produced_at": self.produced_at,
            "mentions": [m.to_object() for m in self.mentions],
            "not_rederivable": NOT_REDERIVABLE,
            "authority": AUTHORITY_FROM_CHECKS,
        }

    def digest(self) -> str:
        return digest_obj(self.to_object())

    def sealed(self) -> dict[str, Any]:
        return {**self.to_object(), "record_digest": self.digest()}


def derive(
    proposer: Proposer, description: str, *, now: datetime
) -> tuple[Proposal, DerivationRecord]:
    """Draft a candidate and record the derivation. Writes nothing anywhere.

    The description is hashed **as received bytes** (E10) — see `studio.descriptions`,
    which stores it without normalising a single byte.
    """
    if proposer.provenance not in (LIVE, FIXTURE):
        raise ProposerUnavailable(
            f"proposer_provenance must be {LIVE!r} or {FIXTURE!r}, not {proposer.provenance!r}"
        )
    proposal = proposer.propose(description)
    instrument = dict(proposer.identity())
    if not instrument:
        raise ProposerUnavailable(
            "the instrument block is empty. A fixture records its own identity, version "
            "and digest exactly as a model records its id — an unrecorded instrument is "
            "an unrecorded derivation."
        )
    record = DerivationRecord(
        description_digest=hashlib.sha256(description.encode("utf-8")).hexdigest(),
        instrument=instrument,
        proposer_provenance=proposer.provenance,
        policy_digest=proposal.policy_digest(),
        produced_at=to_iso(now),
        mentions=list(proposal.mentions),
    )
    return proposal, record


# --- The shipped stand-in ----------------------------------------------------------

_KEYWORDS: dict[str, tuple[str, str]] = {
    "refund": ("refunds.issue", "money.egress"),
    "payment": ("payments.transfer", "money.egress"),
    "transfer": ("payments.transfer", "money.egress"),
    "payout": ("payouts.schedule", "money.egress"),
    "webhook": ("webhooks.post", "net.egress"),
    "invoice": ("invoices.send", "customer.contact"),
    "report": ("reports.read", ""),
}
"""What the fixture proposer recognises. Deliberately small and deliberately dumb.

It is a **stand-in for an instrument**, not a pretend model: it exists so CI can exercise
every path with no key, no network and a reproducible answer. Its misses are real misses
and appear in the published benchmark beside a live run's — a stand-in whose failures were
hidden would make the benchmark a claim about nothing.
"""

FIXTURE_VERSION = "1"

MEASURED = "measured"
ASSERTED = "asserted"
KINDS = (MEASURED, ASSERTED)
"""The two kinds of row this proposal renders, declared rather than spelled in a skin.

`measured` is what the engine observed; `asserted` is what a description *claims*. The
distinction is the whole point of the page — a reader must not mistake a claim for a
measurement — which is exactly why it must not be marked in the brand accent (R056 §4)
and why the seal check has to know these words.

Promoted from literal class names by R057 §6. They were spelled in `viewer/proposal.py`
and declared nowhere, so the check that guards them needed one hand-typed entry beside
a vocabulary derived from every other enumeration. **A vocabulary half-derived and
half-typed drifts from both ends:** type it once, import it everywhere.
"""


class FixtureProposer:
    """A deterministic keyword proposer. Same description in, same candidate out.

    **It labels itself.** `provenance` is `fixture` and rides inside the derivation
    record's digest, so a fixture-drafted candidate cannot be presented as a model's work
    without breaking the record's own address.
    """

    provenance = FIXTURE

    def __init__(self, pack_digest: str | None = None) -> None:
        from onedoor import templates

        self._pack_digest = pack_digest or templates.PACK_DIGEST

    def identity(self) -> dict[str, Any]:
        """Never empty (R053 §2): a stand-in records its identity as a model records its id."""
        return {
            "kind": "fixture",
            "name": "onedoor.studio.proposer.FixtureProposer",
            "version": FIXTURE_VERSION,
            "rules_digest": _prompt_digest(json.dumps(_KEYWORDS, sort_keys=True)),
            "pack_digest": self._pack_digest,
        }

    def propose(self, description: str) -> Proposal:
        """Draft from the shipped pack, keeping only what the description mentions.

        Every rule it emits comes from `templates.PAYMENTS` — a set already asserted to
        satisfy the law family — so the stand-in cannot invent a shape the pack's own
        tests never checked. What it *can* get wrong is which rules to include, which is
        the interesting failure and the one the benchmark publishes.
        """
        from onedoor import templates

        available, effects = templates.PAYMENTS.load()
        by_action = {p.action_type: p for p in available}
        lowered = description.lower()

        chosen: dict[str, Policy] = {}
        mentions: list[Mention] = []
        for keyword, (action, effect) in _KEYWORDS.items():
            if keyword not in lowered:
                continue
            quote = _sentence_containing(description, keyword)
            policy = by_action.get(action)
            if policy is None:
                mentions.append(
                    Mention(subject=action, kind="action_type", quote=quote, covered_by=None)
                )
                continue
            chosen[action] = policy
            if effect:
                mentions.append(
                    Mention(subject=effect, kind="effect", quote=quote, covered_by=action)
                )

        # Every reversal a chosen rule names must come too, or the candidate fails
        # `validate_policy` for a reason the description never mentioned. Fail-closed by
        # construction rather than by the operator noticing.
        for policy in list(chosen.values()):
            reversal = policy.compensating_command
            if reversal and reversal not in chosen and reversal in by_action:
                chosen[reversal] = by_action[reversal]

        needed = {e for p in chosen.values() for e in p.effects}
        needed |= {e for p in chosen.values() for r in p.param_effects for e in r.add_effects}
        return Proposal(
            policies=[chosen[a] for a in sorted(chosen)],
            # Only the effects the chosen rules name — never a bare label, which would be
            # the `declared_inert` defect emitted by our own generator (Q3's law, T7).
            effects=[e for e in effects if e.effect in needed],
            mentions=sorted(mentions, key=lambda m: (m.kind, m.subject)),
        )


def _sentence_containing(text: str, keyword: str) -> str:
    """The description's own words, quoted — never the model's paraphrase of them.

    Principle 2: the explanation derives from the artifact, not from the model's memory.
    A mention that quoted a paraphrase would be the model vouching for itself.
    """
    for chunk in text.replace("\n", ". ").split("."):
        if keyword in chunk.lower():
            return chunk.strip()
    return text.strip()[:120]


def live_proposer(*_args: Any, **_kwargs: Any) -> Proposer:
    """The real client. Not built yet, and it refuses rather than pretending.

    X-6's shape: hard at the point of use, refused with a message naming the remedy. A
    stub that quietly returned the fixture would be the worst possible outcome — a demo
    that looks like a model and is not, which is exactly what `proposer_provenance` exists
    to make impossible.
    """
    raise ProposerUnavailable(
        "no live proposer is configured. `onedoor[studio]` ships the deterministic "
        "FixtureProposer so CI and demos run with no key; a model-backed proposer is a "
        "separate, credentialed component and is not part of this build. Nothing here "
        "falls back to the fixture silently — a demo that looks like a model and is not "
        "is the failure `proposer_provenance` exists to prevent."
    )
