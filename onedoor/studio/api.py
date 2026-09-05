"""`ND-056` / T2 — the policy REST API. Draft CRUD, and no way to approve anything.

## What this is for

Everything the Studio's screens do to a draft, a script can do too: create, read, list,
add or update a rule, remove one, ask what the loader thinks, and submit it for
ratification. It is the same store, through the same parser, with the same refusals —
this module adds an entry point, never a second set of rules.

## Approval is not here, and the reason is not squeamishness

**Ratification stays the human ceremony.** Forward 006 §2 gave the reason and it is
exact: *an approval without a named approver is testimony.* The engine records
`ratified_by_session` — declared, never authenticated — and until actor identity exists
(Q7's `key_id`, ruled in R059 §3 and frozen until the freeze lifts), an API that
ratified would be writing an approval nobody can be held to.

So `submit` sets a flag meaning **a human has been asked**. It moves no version pointer,
writes no receipt, and touches the enforcer's store not at all. The ceremony is a page a
person loads.

### One legacy route exists and this API is not it

`POST /draft/{id}/ratify` has served since `ND-052`/S3-T2 and shipped in `0.6.2`. It
ratifies over HTTP with a declared session string. R066 §1 ruled it stays through this
release — launch week is the wrong week to break a published surface — documented
truthfully, pinned by a witness test, and carrying a deprecation field in its own
response so a caller is told what it is by the thing itself. It retires with the
actor-identity work.

The sentence the docs carry is ruled verbatim and lives in `LEGACY_NOTE` below. It is
true, which is the only reason it is shippable.

## Refusals are typed, and honest as a whole

R059 §2: **a response is honest as a whole — status, media type, body — or not at all.**
Every refusal here answers with a JSON body carrying a `reason` from `REASONS`, and the
status is chosen for what actually happened:

| Status | What it means |
|---|---|
| `404` | there is no such draft or rule — an absence |
| `409` | the request was well-formed and the world declined it (a moved pin, an already-submitted draft) |
| `422` | the parser refused the candidate; the staged refusals are in the body |
| `400` | the request itself was malformed |

`422` and `409` are deliberately different: a candidate the loader refuses is a
statement about the rules, and a stale pin is a statement about the world. Collapsing
them would hand the caller back the ambiguity the ceremony refused to have.
"""

from __future__ import annotations

from typing import Any

from onedoor.guardrail.models import EffectPolicy, Policy
from onedoor.studio import forecast, staging

API_ROOT = "/api/v1"
OPENAPI_PATH = f"{API_ROOT}/openapi.json"
"""Published deliberately (Q12, R066 §5).

V8 turned `openapi_url` off because `/openapi.json` *published an API surface nobody
chose to publish*, and because `/docs` and `/redoc` pulled Swagger, ReDoc, fonts and a
favicon from CDNs — making the header's "nothing leaves this machine" false. T2 is a
surface someone chose, and JSON fetches nothing, so neither half of that finding
survives here. `/docs` and `/redoc` stay off; they are the half that reached the network.
"""

NO_APPROVAL_NOTE = (
    "The v1 API adds no approval route — ratification belongs to the human ceremony. "
    "One legacy route (POST /draft/{id}/ratify), predating actor identity, still "
    "serves; it records its approver as declared, never authenticated, and is retired "
    "with the key_id work."
)
"""R066 §1, verbatim. It is TRUE, which is the only reason it can ship.

The version of this sentence that said the API has no approval route full stop would
have been false while the legacy route serves — and delivery's R2 was that a false
sentence about approval is not shippable.
"""

LEGACY_DEPRECATION = {
    "status": "deprecated",
    "why": (
        "This route predates actor identity. It records the approver as a declared "
        "session string, never an authenticated one, so the receipt names what it was "
        "told rather than who acted."
    ),
    "retired_with": "the actor-identity work (key_id)",
    "instead": "ratify through the ceremony page at /drafts/{draft_id}/ratify",
}
"""Carried in the legacy route's own JSON response (R066 §1).

A caller who uses it is told what it is **by the thing itself**, rather than by
documentation they were never obliged to read.
"""

SUBMIT_MEANS = (
    "A human has been asked to ratify this draft. Nothing has been approved, no version "
    "pointer moved, and no receipt was written. Ratification happens on the ceremony "
    "page."
)

# --- typed refusals -------------------------------------------------------------------

NO_SUCH_DRAFT = "no_such_draft"
NO_SUCH_RULE = "no_such_rule"
CANDIDATE_REFUSED = "candidate_refused"
ALREADY_SUBMITTED = "already_submitted"
MALFORMED_REQUEST = "malformed_request"
BASE_MOVED = "base_moved"

REASONS = (
    NO_SUCH_DRAFT,
    NO_SUCH_RULE,
    CANDIDATE_REFUSED,
    ALREADY_SUBMITTED,
    MALFORMED_REQUEST,
    BASE_MOVED,
)
"""Every reason this API can give, declared once so the tests can be total over them."""

STATUS_FOR = {
    NO_SUCH_DRAFT: 404,
    NO_SUCH_RULE: 404,
    CANDIDATE_REFUSED: 422,
    ALREADY_SUBMITTED: 409,
    MALFORMED_REQUEST: 400,
    BASE_MOVED: 409,
}
"""Reason to status, in one table.

A mapping rather than a status chosen at each raise site: two routes refusing the same
thing with different codes is the sort of drift nobody notices until a client branches
on it.
"""


class ApiRefusal(Exception):
    """A typed refusal. Carries its reason, its status and anything the caller needs."""

    def __init__(self, reason: str, message: str, **extra: Any) -> None:
        if reason not in REASONS:
            raise ValueError(f"unknown API refusal reason: {reason!r}")
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.extra = extra

    @property
    def status(self) -> int:
        return STATUS_FOR[self.reason]

    def body(self) -> dict[str, Any]:
        return {"reason": self.reason, "message": self.message, **self.extra}


# --- representations -------------------------------------------------------------------


def draft_object(draft: Any, *, active_version: str | None) -> dict[str, Any]:
    """One draft as data. The pin's state is a FIELD, not something a client recomputes."""
    return {
        "draft_id": draft.draft_id,
        "title": draft.title,
        "state": draft.state,
        "base_version": draft.base_version,
        "base_moved": draft.base_version != active_version,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "rules": [rule_object(p) for p in draft.policies],
        "effects": [effect_object(e) for e in draft.effects],
    }


def rule_object(policy: Policy) -> dict[str, Any]:
    """A rule as the engine holds it — dumped through the model, never hand-built.

    `model_dump(mode="json")` is what makes the decimal fields render in the canonical
    form the engine stores, so the API and the raw editor pane show the same string for
    the same money. V7 learned that one the hard way, on `'500.00'` against `'500'`.
    """
    return policy.model_dump(mode="json")


def effect_object(effect: EffectPolicy) -> dict[str, Any]:
    return effect.model_dump(mode="json")


def validation_object(
    result: staging.StagedResult, forecasts: tuple[forecast.Forecast, ...]
) -> dict[str, Any]:
    """Both lists as data, and they are separate keys for the same reason they are
    separate panels: merging them would tell a client the loader refuses what it accepts.
    """
    return {
        "loads": result.loads,
        **result.to_object(),
        "forecasts": [f.to_object() for f in forecasts],
        # R092 F-D1: the notice must be true of THIS candidate. "The loader accepts
        # every rule below" is false the moment `result.refusals` is not empty --
        # witnessed on this exact object, `payments.transfer` sitting in `forecasts`
        # while `refusals` two keys up refused it.
        "forecast_notice": forecast.notice(refused=bool(result.refusals)),
        "forecasts_are_not_complete": forecast.FORECASTS_ARE_NOT_COMPLETE,
    }


def parse_rule(payload: Any) -> Policy:
    """One rule, through the ONE parser, with the staged refusals on failure.

    The API does not get its own validator any more than the editor does. A payload that
    `Policy` will not validate comes back as a `422` carrying exactly what the staged
    checker produced for it, so an API caller and a person at the editor are told the
    same thing about the same bytes.
    """
    if not isinstance(payload, dict):
        raise ApiRefusal(
            MALFORMED_REQUEST,
            f"a rule must be a JSON object, got {type(payload).__name__}",
        )
    import json

    result = staging.staged_rule(json.dumps(payload))
    if result.refusals or not result.policies:
        raise ApiRefusal(
            CANDIDATE_REFUSED,
            "the loader would refuse this rule",
            **validation_object(result, ()),
        )
    return result.policies[0]
