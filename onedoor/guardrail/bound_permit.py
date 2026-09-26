"""The issuer side: onedoor signs a bound permit for a permitted action (bound-permit
profile §§3-4, §12).

Deliberately thin. All the actual envelope/binding mechanics (JWS, the action
digest, JCS) live in `onedoor.permit`, the same standalone package the recipient
side uses -- one implementation of each mechanism, never two, on both sides of the
trust boundary this module and `onedoor.permit.recipient` sit on either side of.
This module's own job is just: decide whether to issue one, and fill in the claims
from what onedoor already knows about the decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from onedoor.guardrail.models import ActionRequest, JsonValue, Policy, Tier
from onedoor.permit.action import action_digest
from onedoor.permit.jws import encode as jws_encode

DEFAULT_LIFETIME_SECONDS = 120
"""profile §3.3: absent an `execute_within` deadline, `exp - iat` MUST NOT exceed this."""


class BoundPermitUnavailable(RuntimeError):
    """A bound permit was declared but cannot be issued for this request.

    Raised rather than issuing a bearer permit silently: profile §4.2 forbids a
    bearer permit across a trust boundary, and `present_bound` is a trust-boundary
    obligation by definition. The caller (`decision.py`) treats this the same way
    it treats any other unmet obligation -- a stated denial, not a quiet downgrade.
    """


def issue(
    *,
    request: ActionRequest,
    policy: Policy,
    action_object: dict[str, JsonValue],
    permit_id: str,
    issuer: str,
    issuer_key_id: str,
    issuer_private_key: Any,
    nominal_tier: Tier,
    effective_tier: Tier,
    policy_version: str | None,
    now: datetime,
    lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS,
) -> str:
    """Issue a bound permit JWS, compact form, for one permitted action.

    `action_object` is `A` (profile §4.3): here, onedoor's own decided `params`,
    treated directly as the JSON object the decision was taken about -- the
    natural mapping, since onedoor's params are already the structured decision
    input the same registration would otherwise have to re-derive from a request.
    `authorization_details` is built from the same object, tagged with the
    policy's registered action type.

    Raises `BoundPermitUnavailable` if the request carries no presenter key
    thumbprint: `cnf.jkt` is REQUIRED across a trust boundary (step 2's own
    check), and `present_bound` is exactly that boundary.
    """
    if policy.present_bound is None or policy.bound_permit_action_type is None:
        raise BoundPermitUnavailable("policy declares no present_bound/bound_permit_action_type")
    if not request.presenter_key_thumbprint:
        raise BoundPermitUnavailable(
            "no presenter key thumbprint on the request; cnf.jkt is required across a "
            "trust boundary and present_bound is exactly that boundary"
        )

    iat = now
    exp = iat + timedelta(seconds=min(lifetime_seconds, DEFAULT_LIFETIME_SECONDS))
    claims: dict[str, object] = {
        "iss": issuer,
        "sub": request.presenter_id or f"urn:onedoor:request:{request.request_id}",
        "aud": policy.present_bound,
        "jti": permit_id,
        "iat": int(iat.timestamp()),
        "nbf": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "cnf": {"jkt": request.presenter_key_thumbprint},
        "authorization_details": [{"type": policy.bound_permit_action_type, **action_object}],
        "action_digest": action_digest(action_object),
        "verdict": "permit",
        "tier": {"nominal": int(nominal_tier), "effective": int(effective_tier)},
        "currentness": "time-bounded",
    }
    if policy_version is not None:
        claims["policy_version"] = policy_version
    header: dict[str, object] = {"alg": "EdDSA", "kid": issuer_key_id, "typ": "aadp-permit+jwt"}
    return jws_encode(header, claims, issuer_private_key)
