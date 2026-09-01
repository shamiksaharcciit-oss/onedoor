"""`ND-056` / T3 — the model-backed proposer: bring your own endpoint, or have none.

`proposer.py` built the shape and left the seam: `live_proposer()` raised
`ProposerUnavailable` rather than pretending, because *a demo that looks like a model and
is not* is the failure `proposer_provenance` exists to prevent. This fills the seam.

## What this is not

It is not a policy author. **The model proposes; the policy layer disposes** — the motto
applied to policy itself. What comes back from an endpoint is text; it becomes a
candidate only by surviving the same parser every hand-written draft survives, and it
becomes a POLICY only by surviving the ceremony a person performs.

## The six walls, and where each one lives

1. **Declared instrument** — `Instrument` below is pinned config, and `identity()`
   returns it whole. `proposer.derive` already refuses an empty instrument block; the
   digest of the prompt template is computed here so a changed prompt is a changed
   instrument rather than a silent difference.
2. **The same single parser** — `propose` hands the model's text to `staging.staged`,
   the loader's own four stages. A generation the parser refuses comes back refused,
   with the staged reasons, and **is never repaired**: there is no retry, no rewrite, no
   fixup. `test_no_auto_repair` asserts that structurally.
3. **The ceremony renders what the parser read** — this module returns parsed `Policy`
   objects and, separately, whatever prose the model sent. The screen renders the first
   as rules and labels the second as the model's own summary. They never merge.
4. **BYO, opt-in, off by default** — `from_env` returns `None` when nothing is
   configured, and the Studio then omits the feature rather than breaking in it. There
   are no bundled credentials and no default provider; the endpoint, the model name and
   the key all come from the operator.
5. **Capability language** — `CAPABILITY` is the one sentence, used everywhere.
6. **The dark-surface list** — `Proposal.mentions` carries what the description
   mentioned that got no rule, quoting the description's own words. Constitution
   principle 4, and R066 §4 confirmed it binds.

## Why stdlib and not `httpx`

One POST. The `[studio]` extra should not grow an HTTP client for it, and `httpx` is a
`[dev]` dependency — a runtime feature resting on a test dependency is the packaging
defect `tests/test_packaging.py` exists to catch. `urllib.request` is in the standard
library and does exactly one thing here.

## What is NOT claimed

A proposal is **not recomputable**: the same description through the same model twice may
differ. Recording the instrument pins the conditions, never the output — which is why
this emits a `DerivationRecord` and not a receipt, and why principle 5 was amended rather
than stretched (R053 §1). `NOT_REDERIVABLE` and `AUTHORITY_FROM_CHECKS` travel with every
rendering.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from onedoor.guardrail.models import Policy
from onedoor.studio import proposer, staging

CAPABILITY = "drafts proposed by a model, ratified by you"
"""The exact words, on every surface that mentions this feature (Forward 006 §2, wall 5).

One constant, because two spellings of one claim are two claims. What it must never
become is any sentence in which the model is the author of a policy: the model produces
a candidate document, a person ratifies it, and the gap between those is the entire
product.
"""

CAPABILITY_FORBIDDEN = (
    "ai writes",
    "ai-written",
    "writes your policies",
    "writes your policy",
    "generates your policies",
    "generates your policy",
    "automatically creates",
    "automatically writes",
    "self-writing",
    "no human",
    "hands-free",
)
"""Phrasings this feature may never carry, held as a test over every T3 surface.

Each one either makes the model the author or removes the person. The list is a fence
around wall 5 rather than a style guide — R063 §3's pattern, where the wording is pinned
by a test instead of by whoever reviews the next edit.
"""

ENV_ENDPOINT = "ONEDOOR_PROPOSER_ENDPOINT"
ENV_MODEL = "ONEDOOR_PROPOSER_MODEL"
ENV_KEY = "ONEDOOR_PROPOSER_KEY"
ENV_TIMEOUT = "ONEDOOR_PROPOSER_TIMEOUT"

TOOL_NAME = "submit_policy_set"
"""The tool's name, and it deliberately does not repeat its parameter's (R081 §2).

It was `propose_policies`, whose top-level parameter is also `policies`. **A parameter
whose name collides with its tool's action verb is ambiguous by construction** — a
reviewer would flag it without ever seeing a benchmark — and the model resolved the
ambiguity the wrong way, serialising the whole envelope into the field as a JSON string.

The parameter could not move: the arguments ARE the policy document, and
`staging.staged` reads its rules from `raw["policies"]`. So the collision comes off the
tool-name side, and the name now states an ACTION over a payload the array obviously is.
"""

_PROMPT_SOURCE = """You are given a description of what an operator wants an AI agent to be allowed to do.

Call the `{tool}` tool exactly once with the policy set you would propose.

Judgement to apply:
- Every policy needs `action_type` and `tier` (1 auto, 2 auto-capped, 3 confirm, 4 deny).
- Tier 1 and tier 2 REQUIRE `compensating_command` naming a reversal action.
- If you declare `cost_param`, list that same parameter under `bounds.required`.
- Prefer the most restrictive tier that satisfies the description.
- Do not invent action types the description does not imply. If the description implies
  none, propose none.

Description:
{description}
"""

PROMPT_TEMPLATE = _PROMPT_SOURCE.replace("{tool}", TOOL_NAME)
"""The prompt, pinned and digested into the instrument.

Changing a word here changes `prompt_digest`, so it changes the instrument — which is
the point. A prompt is part of what produced the candidate, and an instrument that did
not include it would attest less than it appears to.

**It no longer asks for a format, because the format is no longer requested — it is
enforced** (R079 §1). The previous version said "Return ONLY a YAML document"; the model
returned a markdown-fenced block on 11 of 11 calls and the loader refused every one at
the first backtick. The prompt now carries only the JUDGEMENT to apply; the shape is the
tool schema's job, and a schema described in prose was never a schema.
"""


MAX_COMPLETION_TOKENS = 2048
"""The completion ceiling, pinned and sent on every request (R076 §2).

**Before this, the request body carried no `max_tokens` at all**, so completion length was
set entirely by whatever the provider's default happened to be — a constant nobody here
chose, that differs between providers and can change server-side without notice. That is
an **unpinned instrument parameter**, and the declared-instrument doctrine puts generation
parameters inside the instrument's declaration. It was found by writing the cost sheet:
the token envelope had to say "not a ceiling on a runaway completion" because there was no
ceiling to state.

**Why 2048.** The fixture's largest correct answer for this corpus is 1,406 characters —
roughly 350–560 tokens across the two ratios the cost sheet used. 2048 gives every correct
answer several times its room while converting the runaway case from *unbounded* to
*bounded and recorded*. A completion that hits the ceiling and arrives structurally broken
is a recorded miss with its refusing stage, which is exactly what the harness now does
with one.
"""


STRICT_ARGUMENTS = True
"""Ask the endpoint to validate arguments against the schema, not merely to route through it.

`tool_choice` enforces EMISSION — the model must answer through the tool, which is what
killed the markdown fence. It does not enforce ARGUMENTS: the endpoint passed through a
payload the schema forbade. This requests the missing half.

**Whether the compatibility layer honours it is a fact to be probed, not assumed**, and
the system is correctly enforced either way (R081 §4): emission is directed, the schema is
unambiguous, argument validation is requested, and the loader catches whatever survives as
a recorded miss. Layered, with a backstop that never launders malformed output into shape.
"""

OUTPUT_ENFORCEMENT = "tool_call"
"""How the output's shape is enforced, recorded in the instrument.

The value names a mechanism, not an intention. `prose` — asking for a format in the
prompt — is what the previous instrument did, and it is not enforcement at all.
"""


def output_schema() -> dict[str, Any]:
    """The schema the model must emit against — **generated from the engine's own models.**

    Not hand-written. `Policy.model_json_schema()` is the same class the loader constructs
    with, so the shape the model is held to and the shape the loader accepts cannot drift:
    a field added to `Policy` appears here without anyone remembering to add it, and a
    hand-copied schema would be the transcription defect wearing JSON.

    `$defs` is hoisted to the root so the `$ref`s Pydantic emits resolve inside the
    wrapper. Effects are described as the loader reads them — a mapping of effect name to
    its settings — rather than as a list, because that is the document's actual shape.
    """
    policy = Policy.model_json_schema()
    defs = policy.pop("$defs", {})
    caps = defs.get("Caps", {"type": "object"})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "policies": {
                "type": "array",
                "description": (
                    "An ARRAY of rule objects, one per action type the description "
                    "implies. May be empty. Never a string, and never a nested document."
                ),
                "items": policy,
            },
            "effects": {
                "type": "object",
                "description": "Effect name to its settings. Every effect a rule names "
                "should have an entry here, or the label is inert.",
                "additionalProperties": {
                    "type": "object",
                    "properties": {"min_tier": {"type": "integer"}, "caps": caps},
                },
            },
        },
        "required": ["policies"],
        "$defs": defs,
    }


def schema_digest() -> str:
    """The schema's address, recorded in the instrument beside the prompt's.

    A changed schema is a changed instrument for exactly the reason a changed prompt is:
    it is part of what produced the candidate. Canonicalised by sorting keys so the digest
    tracks the schema's content rather than Python's dict ordering.
    """
    return hashlib.sha256(
        json.dumps(output_schema(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def prompt_digest() -> str:
    return hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Instrument:
    """What produced a proposal, pinned. Never empty, and never inferred at render time."""

    endpoint: str
    model: str
    timeout_seconds: float = 30.0
    max_completion_tokens: int = MAX_COMPLETION_TOKENS
    strict_arguments: bool = STRICT_ARGUMENTS
    """Whether argument-level schema validation was REQUESTED of the endpoint.

    Recorded because it is part of what produced the candidate, and because "we asked"
    and "the layer honoured it" are different facts: this field states the first, and only
    the first. What the layer actually did is a probe result, not a configuration value.
    """
    """Pinned, sent on every request, and recorded in `identity()` (R076 §2).

    It is a field rather than a constant read at the call site so that a deployment which
    changes it **cannot change it quietly**: the value rides in the instrument block, the
    instrument block rides inside the derivation record's digest, and a different ceiling
    is therefore a different instrument. That is the declared-instrument doctrine applied
    to a generation parameter.
    """

    @property
    def host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.endpoint).netloc or self.endpoint

    def identity(self) -> dict[str, Any]:
        """The instrument block. **The key is deliberately absent.**

        A credential in a record is a credential in a record, and a DIGEST of a
        credential is still a function of the credential — R059 §3's ruling on
        `actor_hash`, which binds here with full force. What is recorded is what was
        used, never what authorised it.

        `max_completion_tokens` is here for the opposite reason: it is a parameter that
        shaped the output, so it belongs in the record of what produced it. A generation
        parameter left out of the instrument would make two runs under different ceilings
        indistinguishable in the record.
        """
        return {
            "kind": "http",
            "endpoint_host": self.host,
            "model": self.model,
            "prompt_digest": prompt_digest(),
            "max_completion_tokens": self.max_completion_tokens,
            # How the shape was enforced, and the shape itself. Both are part of what
            # produced the candidate, so both are part of the instrument (R079 section 3).
            "output_enforcement": OUTPUT_ENFORCEMENT,
            "strict_arguments_requested": self.strict_arguments,
            "schema_digest": schema_digest(),
        }


ProposalRefused = proposer.ProposalRefused
"""Re-exported from `proposer`, where it now lives (R071 section 5).

It moved so `benchmark` can catch a refused generation without importing this module: the
benchmark scores ANY instrument, and a dependency from it to the model-backed proposer
would tie it to a track that may slip to a later release. The name stays here because
callers of this module reasonably look for it here.
"""


class HttpProposer:
    """A model behind an OpenAI-shaped chat endpoint the operator supplies.

    `provenance` is `live`, and it rides inside the derivation record's digest, so a
    candidate drafted here cannot be relabelled as a fixture's work — or a fixture's as
    this — without breaking the record's own address.
    """

    provenance = proposer.LIVE

    def __init__(self, instrument: Instrument, *, api_key: str | None = None) -> None:
        self.instrument = instrument
        self._api_key = api_key

    def identity(self) -> dict[str, Any]:
        return self.instrument.identity()

    def propose(self, description: str) -> proposer.Proposal:
        """Ask the endpoint, then hand what comes back to the ONE parser.

        Everything between those two acts is transport. There is deliberately no step
        that inspects the text and decides whether it looks like policy: that judgement
        belongs to `staging`, which is the loader, and a second opinion here would be the
        second validator wearing a client's clothes.
        """
        text = self._ask(PROMPT_TEMPLATE.format(description=description))
        return self.parse(text, description)

    def parse(self, text: str, description: str) -> proposer.Proposal:
        """The model's text through the loader's own stages. No repair, ever.

        A generation the parser refuses is REFUSED — shown with reasons, never quietly
        rewritten into something that parses. Stripping a stray fence or fixing an indent
        would be this module deciding what the model meant, which is exactly the
        authority it does not have.
        """
        result = staging.staged(text)
        if not result.loads:
            raise ProposalRefused("the loader would refuse the generated policy set", result, text)
        mentions = _mentions_for(result.policies, description)
        return proposer.Proposal(
            policies=list(result.policies),
            effects=list(result.effects),
            mentions=mentions,
        )

    def _ask(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.instrument.model,
                "messages": [{"role": "user", "content": prompt}],
                # Pinned, never the provider's default (R076 §2). Read from the
                # instrument rather than the module constant so the value that shaped
                # the output is the same value the record carries.
                "max_tokens": self.instrument.max_completion_tokens,
                # The schema is ENFORCED at emission, not requested in prose (R079 §1).
                # `tool_choice` names the function rather than leaving the model free to
                # answer in text: a tool the model may decline is a request again.
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": TOOL_NAME,
                            "description": "Submit the proposed policy set.",
                            "parameters": output_schema(),
                            # The argument-level half of the enforcement (R081 §2).
                            # Requested rather than assumed; if the layer ignores it the
                            # loader is still the backstop and nothing is laundered.
                            "strict": self.instrument.strict_arguments,
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": TOOL_NAME}},
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(  # noqa: S310 - the operator supplies this URL
            self.instrument.endpoint, data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - same
                request, timeout=self.instrument.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise proposer.ProposerUnavailable(
                f"the configured proposer endpoint did not answer: {exc}. Nothing was "
                "drafted, and nothing about this is a statement that your description "
                "is bad."
            ) from exc
        return _content_of(body)


def _content_of(body: Any) -> str:
    """The tool call's arguments out of an OpenAI-shaped response, refused if absent.

    **Three outcomes, and the middle one is the whole reason this changed.**

    - A tool call with an `arguments` string — returned **verbatim**, straight to the one
      parser. It is JSON, and JSON is loadable YAML, so `staging.staged` reads it with no
      transformation whatsoever. Enforcement at emission does **not** replace validation:
      the loader still decides, exactly as it does for a hand-written draft.
    - **No tool call at all** — the endpoint did not honour `tool_choice`, so the schema
      was not enforced. That is `unavailable`: a fact about the endpoint's capability, not
      a verdict on the model's judgement, and emphatically not a refused proposal. An
      endpoint that ignores the enforcement surface must be discovered as a provisioning
      problem rather than scored as eleven bad answers.
    - Arguments present but not valid JSON — returned as-is anyway, so **`staging` refuses
      it and it is recorded as the malformed miss it is.** This module does not get a
      second opinion about whether the model's output is well-formed; that judgement has
      exactly one owner.
    """
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise proposer.ProposerUnavailable(
            "the endpoint answered in a shape this build cannot read (expected an "
            "OpenAI-style `choices[0].message`). Nothing was drafted; this is not a "
            "statement that the model produced nothing."
        ) from exc

    calls = message.get("tool_calls") if isinstance(message, dict) else None
    if not calls:
        raise proposer.ProposerUnavailable(
            f"the endpoint returned no tool call, so the {TOOL_NAME!r} schema was not "
            "enforced on this answer. The request pinned `tool_choice` to that function, "
            "so this is a statement about what the endpoint supports, not about what the "
            "model proposed. Nothing was drafted."
        )
    try:
        arguments = calls[0]["function"]["arguments"]
    except (KeyError, IndexError, TypeError) as exc:
        raise proposer.ProposerUnavailable(
            "the endpoint returned a tool call this build cannot read (expected "
            "`tool_calls[0].function.arguments`). Nothing was drafted."
        ) from exc
    if not isinstance(arguments, str):
        raise proposer.ProposerUnavailable(
            f"the tool call's arguments are {type(arguments).__name__}, not text"
        )
    return arguments


def _mentions_for(policies: Any, description: str) -> list[proposer.Mention]:
    """The dark-surface list: what the description named that got no rule (wall 6).

    Constitution principle 4 — *non-coverage is stated, never silent*. The quote is the
    description's OWN words, never a paraphrase: a mention that quoted the model's
    summary would be the model vouching for itself (principle 2).

    Detection is deliberately dumb and deliberately declared: a word in the description
    that looks like an action reference and matches no rule's action type. It finds less
    than a model would; what it finds is checkable, which is the trade this product makes
    everywhere.
    """
    declared = {p.action_type for p in policies}
    declared_words = {
        _singular(part) for action in declared for part in action.replace(".", " ").split()
    }
    out: list[proposer.Mention] = []
    seen: set[str] = set()
    for raw in description.replace("\n", " ").split():
        word = raw.strip(".,;:!?()[]\"'").lower()
        if len(word) < 4 or word in seen or _singular(word) in declared_words:
            continue
        if word in _ACTIONISH:
            seen.add(word)
            out.append(
                proposer.Mention(
                    subject=word,
                    kind="action_type",
                    quote=_sentence_with(description, word),
                    covered_by=None,
                )
            )
    return sorted(out, key=lambda m: m.subject)


_ACTIONISH = frozenset(
    {
        "refund",
        "refunds",
        "payment",
        "payments",
        "transfer",
        "transfers",
        "payout",
        "payouts",
        "invoice",
        "invoices",
        "webhook",
        "webhooks",
        "email",
        "emails",
        "delete",
        "deletion",
        "export",
        "exports",
        "publish",
        "deploy",
        "shutdown",
        "restart",
    }
)
"""Words that usually name something an agent DOES.

Small, declared, and knowingly incomplete — `FORECASTS_ARE_NOT_COMPLETE`'s sibling. The
list's misses are real misses and belong in the published benchmark beside a live run's,
which is what the constitution's §2 bar asks for.
"""


def _singular(word: str) -> str:
    """`refunds` and `refund` are the same subject, and nothing more clever than that.

    Without this, a description saying "refunds" against a declared `payments.refund`
    reported the refunds as UNCOVERED -- a false gap, which is worse than a missed one:
    a list that cries wolf is a list an operator learns to skim. A declared, one-line
    transformation is admissible where a similarity score is not (Core Note, 2026-08-30:
    *never a score, always a declared transform*).
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _sentence_with(text: str, word: str) -> str:
    for chunk in text.replace("\n", ". ").split("."):
        if word in chunk.lower():
            return chunk.strip()
    return text.strip()[:120]


def from_env(env: dict[str, str] | None = None) -> HttpProposer | None:
    """Build a proposer from configuration, or return `None` if there is none.

    **`None` is the default and it means ABSENT, not broken.** With no endpoint
    configured the Studio omits the feature entirely — no tab, no route, no mention —
    rather than rendering a control that would fail when used. A page that offers
    something this deployment cannot do is the right-typed lie as a button.

    Nothing falls back to `FixtureProposer`. That would be a demo that looks like a model
    and is not, which is the one outcome `proposer_provenance` exists to prevent.
    """
    source = os.environ if env is None else env
    endpoint = (source.get(ENV_ENDPOINT) or "").strip()
    model = (source.get(ENV_MODEL) or "").strip()
    if not endpoint or not model:
        return None
    try:
        timeout = float(source.get(ENV_TIMEOUT) or 30.0)
    except ValueError:
        timeout = 30.0
    return HttpProposer(
        Instrument(endpoint=endpoint, model=model, timeout_seconds=timeout),
        api_key=(source.get(ENV_KEY) or "").strip() or None,
    )
