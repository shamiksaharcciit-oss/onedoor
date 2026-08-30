"""`ND-056` / T1 — the loader's boot path, run over text, one stage at a time.

`validate.problems` answers *"what would `validate_policy` refuse?"* for a candidate that
has **already been built into `Policy` objects**. That is the last of the four things the
loader does at boot, and until now it was the only one the Studio could reach — because
the editor hands it constructed models, so a file that never parses, or never validates
against the schema, could not be shown a problem at all. Upload changes the entry point:
bytes come in at the top of the loader's path, so the whole path becomes reachable.

## The four stages, which are the loader's own and in the loader's own order

| Stage | The loader's function | What it refuses |
|---|---|---|
| `load` | `policy_loader._safe_load_decimal` | YAML syntax, a file that is not a mapping, a non-finite number |
| `schema` | `policy_loader._policy_from_entry` | anything `Policy` will not validate |
| `rules` | `policy_loader.validate_policy` | the per-rule rules |
| `effects` | `EffectPolicy` construction | a bad tier, caps that will not validate |

**`rules` comes before `effects` because that is the order `load_file` uses**, and the
order is not cosmetic: it decides which stage a candidate with two kinds of defect is
reported against. This module first had `effects` third, on the reasonable-sounding
assumption that a candidate is built before it is judged. `load_file` does the opposite —
*"validate all first"*, then build the effect policies — so a file with both a bad effect
tier and a tier-2 rule missing its reversal would have been reported as stopping at
`effects` while the engine would stop at `rules`. A stage name that names the wrong stage
is a right-typed lie about the loader. Caught by writing the AST fence below, which is
the fence doing its job before it had run once.

**Nothing here decides anything.** Every refusal below is produced by calling an engine
function and catching what it raised; this module chooses the order (which is the
loader's) and the presentation (which is the Studio's job). A stage that reached its own
verdict would be the second validator `validate.py` exists not to be, and it would
disagree with the loader in the direction that lets a bad rule through.

`test_staging_matches_the_loader.py` walks `load_file`'s AST and asserts it calls exactly
these functions in exactly this order, so the two cannot drift apart silently. The table
above is a claim about `load_file`, and a claim about code is a test.

## Why a stage stops the ones after it

`STAGES` is ordered, and the first stage that produces a refusal is the last stage that
runs. Not an optimisation — a correctness requirement. Stage `schema` cannot run on a
document stage `load` could not parse, and stage `rules` cannot run on a `Policy` that
was never constructed. Running them anyway would mean inventing an object to check, and
a refusal computed against an invented object is a statement about nothing.

So the result names the stage it stopped at, and the reader is told the later stages did
not run rather than being allowed to read their silence as a pass. **Silence from a
stage that never ran is not a clean bill.**

## What this still does not promise

`INCOMPLETE_NOTICE` is unchanged and still binds: `validate_policy` stops at the **first
failure per rule**, and set-level defects are invisible to a per-rule loop. Reaching
three more stages widens what can be found; it does not make the list complete, and no
wording here says it does. The honest sentence, ruled in R066 §3:

> every refusal the loader can produce for this candidate, at the stage that produces
> it — first failure per rule, set-level defects still invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import ValidationError

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Caps, EffectPolicy, Policy, Tier
from onedoor.studio import validate

STAGE_LOAD = "load"
STAGE_SCHEMA = "schema"
STAGE_EFFECTS = "effects"
STAGE_RULES = "rules"

STAGES = (STAGE_LOAD, STAGE_SCHEMA, STAGE_RULES, STAGE_EFFECTS)
"""The loader's order, declared once. The renderer reads this rather than spelling it.

A vocabulary half-derived and half-typed drifts from both ends (R057 §6), and the stage
names appear on the page, in the API's JSON and in the tests.

The order is asserted against `load_file`'s AST by
`tests/studio/test_staging_matches_the_loader.py`, so this tuple cannot quietly stop
describing the engine.
"""

STAGE_LABELS = {
    STAGE_LOAD: "reading the file",
    STAGE_SCHEMA: "checking each rule against the schema",
    STAGE_RULES: "applying the per-rule rules",
    STAGE_EFFECTS: "building the effect policies",
}

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
ABSENT = "absent"
POSITION_STATES = (RESOLVED, UNRESOLVED, ABSENT)
"""Three outcomes for a position, and they never collapse into two.

`resolved` — the parser told us where. `unresolved` — the problem names a path and no
node mark could be found for it. `absent` — the problem is about the document as a
whole and has no position by nature.

**A guessed line 1 is worse than no line at all**: it sends a reader to a place the
problem is not, and it looks exactly like a resolved position while doing it. So an
unresolved position says so in those words and gives no number.
"""

UNRESOLVED_WORDING = "position not resolved"
ABSENT_WORDING = "applies to the whole file"

STOPPED_NOTICE = (
    "Checking stopped at this stage. The stages after it did not run, so they found "
    "nothing because they were not asked — not because there is nothing to find."
)
"""Rendered whenever `stopped_at` is set. The silence of a stage that never ran is the
easiest thing on this page to misread as a pass, so the page says it outright."""


@dataclass(frozen=True)
class Position:
    """Where a refusal is, in three outcomes."""

    state: str
    line: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if self.state not in POSITION_STATES:
            raise ValueError(f"position state must be one of {POSITION_STATES}, not {self.state!r}")
        if self.state != RESOLVED and (self.line is not None or self.column is not None):
            # A number on a non-resolved position is the fabricated line 1 arriving by
            # a different door: whatever the state says, a reader believes the number.
            raise ValueError("only a resolved position carries a line and column")
        if self.state == RESOLVED and self.line is None:
            raise ValueError("a resolved position must carry a line")

    def describe(self) -> str:
        if self.state == RESOLVED:
            where = f"line {self.line}"
            return f"{where}, column {self.column}" if self.column is not None else where
        return UNRESOLVED_WORDING if self.state == UNRESOLVED else ABSENT_WORDING

    def to_object(self) -> dict[str, Any]:
        return {"state": self.state, "line": self.line, "column": self.column}


@dataclass(frozen=True)
class Refusal:
    """One thing the loader would refuse at boot, and the stage that would refuse it."""

    stage: str
    message: str
    position: Position
    action_type: str | None = None
    """`None` for a refusal about the document rather than about one rule."""

    def to_object(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "action_type": self.action_type,
            "message": self.message,
            "position": self.position.to_object(),
        }


RULE_STAGES = (STAGE_LOAD, STAGE_SCHEMA, STAGE_RULES)
"""The stages that apply to ONE rule rather than a whole file.

A single rule declares no effect policies, so the `effects` stage is **not applicable**
rather than passed. Reporting it as passed would be the same lie as reporting a stage
that never ran as clean — the editor's raw pane holds a rule, and a rule cannot carry an
effects block for the stage to check.
"""


@dataclass(frozen=True)
class StagedResult:
    """What the loader would do with this text, and how far the checking got.

    `stages` is the set that APPLIES to the input, not a global constant: a whole file
    gets four, one rule gets three. A result that always claimed four would report the
    effects stage as silently passed on a rule that could never have had one.
    """

    stopped_at: str | None
    refusals: tuple[Refusal, ...]
    policies: tuple[Policy, ...]
    effects: tuple[EffectPolicy, ...]
    stages: tuple[str, ...] = STAGES

    @property
    def stages_run(self) -> tuple[str, ...]:
        if self.stopped_at is None:
            return self.stages
        return self.stages[: self.stages.index(self.stopped_at) + 1]

    @property
    def stages_not_run(self) -> tuple[str, ...]:
        return tuple(s for s in self.stages if s not in self.stages_run)

    @property
    def loads(self) -> bool:
        """True when every stage ran and refused nothing — what the loader would accept."""
        return self.stopped_at is None and not self.refusals

    def to_object(self) -> dict[str, Any]:
        return {
            "stopped_at": self.stopped_at,
            "stages": list(self.stages),
            "stages_run": list(self.stages_run),
            "stages_not_run": list(self.stages_not_run),
            "refusals": [r.to_object() for r in self.refusals],
            "incomplete_notice": validate.INCOMPLETE_NOTICE,
        }


# --- positions ---------------------------------------------------------------------


def _compose(text: str) -> yaml.Node | None:
    """The document's node tree, for marks only — the loader's own parser, not a rescan.

    Constructors never run here, so this cannot disagree with the load stage about what
    the document *means*; it is asked only where things are. A document that will not
    compose returns `None` and every position becomes `unresolved`, which is the honest
    outcome rather than an excuse to guess.
    """
    try:
        composed: yaml.Node | None = yaml.compose(text, Loader=policy_loader._DecimalSafeLoader)
    except yaml.YAMLError:
        return None
    return composed


def _child(node: yaml.Node | None, key: str | int) -> yaml.Node | None:
    if node is None:
        return None
    if isinstance(key, int):
        if isinstance(node, yaml.SequenceNode) and 0 <= key < len(node.value):
            child: yaml.Node = node.value[key]
            return child
        return None
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                found: yaml.Node = v
                return found
    return None


def _position(root: yaml.Node | None, path: tuple[str | int, ...]) -> Position:
    """Walk `path` from the document root and report where it landed.

    Falls back to the deepest ancestor that *did* resolve, because pointing at the rule
    that contains the problem is a true statement about where to look, while pointing at
    line 1 is not. If not even the first step resolves, the position is `unresolved`.
    """
    node = root
    deepest: yaml.Node | None = root if root is not None else None
    for key in path:
        node = _child(node, key)
        if node is None:
            break
        deepest = node
    if deepest is None or deepest is root and path:
        return Position(UNRESOLVED) if root is None or path else Position(ABSENT)
    mark = deepest.start_mark
    return Position(RESOLVED, line=mark.line + 1, column=mark.column + 1)


def _mark_position(mark: Any) -> Position:
    """A position from a PyYAML mark, which is 0-based and may be absent."""
    if mark is None:
        return Position(UNRESOLVED)
    return Position(RESOLVED, line=int(mark.line) + 1, column=int(mark.column) + 1)


def _loc_path(loc: tuple[Any, ...]) -> tuple[str | int, ...]:
    """A pydantic error location, narrowed to the parts that address YAML nodes."""
    out: list[str | int] = []
    for part in loc:
        if isinstance(part, int | str):
            out.append(part)
    return tuple(out)


# --- the stages, shared by both entry points -----------------------------------------


def _stage_schema(
    root: yaml.Node | None,
    entries: list[Any],
    prefix: tuple[str | int, ...],
) -> tuple[list[Refusal], list[Policy]]:
    """`_policy_from_entry` over each entry, with positions rooted at `prefix`.

    `prefix` is what lets one rule and a whole file share this code without either
    borrowing the other's line numbers: a file's entries live under `("policies", i)`,
    and the editor's single rule IS the document, so its prefix is empty. Wrapping the
    rule in a synthetic `policies:` list would have been simpler and would have shifted
    every position the operator is shown — a fabricated position arriving by arithmetic.
    """
    refusals: list[Refusal] = []
    policies: list[Policy] = []
    for index, entry in enumerate(entries):
        at = prefix + ((index,) if prefix else ())
        named = entry.get("action_type") if isinstance(entry, dict) else None
        action_type = named if isinstance(named, str) else None
        if not isinstance(entry, dict):
            refusals.append(
                Refusal(
                    stage=STAGE_SCHEMA,
                    message=f"a rule must be a mapping, got {type(entry).__name__}",
                    position=_position(root, at),
                )
            )
            continue
        try:
            policies.append(policy_loader._policy_from_entry(entry))
        except ValidationError as exc:
            for error in exc.errors():
                loc = _loc_path(tuple(error.get("loc", ())))
                refusals.append(
                    Refusal(
                        stage=STAGE_SCHEMA,
                        action_type=action_type,
                        message=_schema_message(loc, str(error.get("msg", "invalid"))),
                        position=_position(root, (*at, *loc)),
                    )
                )
    return refusals, policies


def _stage_rules(
    root: yaml.Node | None,
    entries: list[Any],
    prefix: tuple[str | int, ...],
    policies: list[Policy],
) -> tuple[Refusal, ...]:
    """`validate.problems` — the existing wrapper — with a position added per rule.

    No effects are passed, because `load_file` has not built any at this point either,
    and `problems` documents that it does not consult them.
    """
    index_by_action = {
        str(entry.get("action_type")): i
        for i, entry in enumerate(entries)
        if isinstance(entry, dict)
    }
    out = []
    for problem in validate.problems(policies):
        if problem.action_type in index_by_action:
            index = index_by_action[problem.action_type]
            at = prefix + ((index,) if prefix else ())
            position = _position(root, at)
        else:
            position = Position(UNRESOLVED)
        out.append(
            Refusal(
                stage=STAGE_RULES,
                action_type=problem.action_type,
                message=problem.message,
                position=position,
            )
        )
    return tuple(out)


def staged_rule(text: str) -> StagedResult:
    """Stage ONE rule — the editor's raw pane, which holds a rule and not a file.

    Three stages, not four: a rule declares no effect policies, so `effects` is not
    applicable rather than passed (`RULE_STAGES`). Positions are relative to the text the
    operator is actually looking at, because the rule is the whole document here.
    """
    root = _compose(text)
    try:
        raw = policy_loader._safe_load_decimal(text)
    except yaml.MarkedYAMLError as exc:
        return StagedResult(
            stopped_at=STAGE_LOAD,
            refusals=(
                Refusal(
                    stage=STAGE_LOAD,
                    message=str(exc.problem or exc).strip(),
                    position=_mark_position(exc.problem_mark or exc.context_mark),
                ),
            ),
            policies=(),
            effects=(),
            stages=RULE_STAGES,
        )
    except (yaml.YAMLError, ValueError) as exc:
        return StagedResult(
            stopped_at=STAGE_LOAD,
            refusals=(Refusal(stage=STAGE_LOAD, message=str(exc), position=Position(ABSENT)),),
            policies=(),
            effects=(),
            stages=RULE_STAGES,
        )

    entries: list[Any] = [raw]
    schema_refusals, policies = _stage_schema(root, entries, ())
    if schema_refusals:
        return StagedResult(
            stopped_at=STAGE_SCHEMA,
            refusals=tuple(schema_refusals),
            policies=(),
            effects=(),
            stages=RULE_STAGES,
        )

    rule_refusals = _stage_rules(root, entries, (), policies)
    return StagedResult(
        stopped_at=STAGE_RULES if rule_refusals else None,
        refusals=rule_refusals,
        policies=tuple(policies),
        effects=(),
        stages=RULE_STAGES,
    )


def staged(text: str) -> StagedResult:
    """Run the loader's boot path over `text` and report at the stage that refused.

    Never writes, never touches a connection, and never constructs a verdict of its own.
    """
    root = _compose(text)

    # Stage 1 -- load. `_safe_load_decimal` is the loader's, including its non-finite
    # refusal, which arrives as a ConstructorError carrying its own mark.
    try:
        raw = policy_loader._safe_load_decimal(text)
    except yaml.MarkedYAMLError as exc:
        return StagedResult(
            stopped_at=STAGE_LOAD,
            refusals=(
                Refusal(
                    stage=STAGE_LOAD,
                    message=str(exc.problem or exc).strip(),
                    position=_mark_position(exc.problem_mark or exc.context_mark),
                ),
            ),
            policies=(),
            effects=(),
        )
    except yaml.YAMLError as exc:
        return StagedResult(
            stopped_at=STAGE_LOAD,
            refusals=(Refusal(stage=STAGE_LOAD, message=str(exc), position=Position(ABSENT)),),
            policies=(),
            effects=(),
        )
    except ValueError as exc:
        # "policy file must be a mapping, got list" -- about the document, so no position.
        return StagedResult(
            stopped_at=STAGE_LOAD,
            refusals=(Refusal(stage=STAGE_LOAD, message=str(exc), position=Position(ABSENT)),),
            policies=(),
            effects=(),
        )

    # Stage 2 -- schema.
    entries = raw.get("policies", [])
    if not isinstance(entries, list):
        return StagedResult(
            stopped_at=STAGE_SCHEMA,
            refusals=(
                Refusal(
                    stage=STAGE_SCHEMA,
                    message=(f"`policies` must be a list of rules, got {type(entries).__name__}"),
                    position=_position(root, ("policies",)),
                ),
            ),
            policies=(),
            effects=(),
        )

    schema_refusals, policies = _stage_schema(root, entries, ("policies",))
    if schema_refusals:
        return StagedResult(
            stopped_at=STAGE_SCHEMA,
            refusals=tuple(schema_refusals),
            policies=(),
            effects=(),
        )

    # Stage 3 -- the per-rule rules. `load_file` validates every policy BEFORE it builds
    # the effect policies, so this runs third and `effects` runs fourth. `validate.problems`
    # is the existing wrapper; this adds only the position, by finding the rule the problem
    # was attributed to. No effects are passed, because none are built yet at this point in
    # the loader either -- and `problems` documents that it does not consult them.
    rule_refusals = _stage_rules(root, entries, ("policies",), policies)
    if rule_refusals:
        return StagedResult(
            stopped_at=STAGE_RULES,
            refusals=rule_refusals,
            policies=tuple(policies),
            effects=(),
        )

    # Stage 4 -- effects. Built exactly as `load_file` builds them.
    effect_entries = raw.get("effects", {}) or {}
    if not isinstance(effect_entries, dict):
        return StagedResult(
            stopped_at=STAGE_EFFECTS,
            refusals=(
                Refusal(
                    stage=STAGE_EFFECTS,
                    message=(
                        f"`effects` must be a mapping of effect name to settings, got "
                        f"{type(effect_entries).__name__}"
                    ),
                    position=_position(root, ("effects",)),
                ),
            ),
            policies=tuple(policies),
            effects=(),
        )

    effect_refusals: list[Refusal] = []
    effects: list[EffectPolicy] = []
    for name, cfg in effect_entries.items():
        try:
            settings = cfg or {}
            if not isinstance(settings, dict):
                raise ValueError(f"effect settings must be a mapping, got {type(cfg).__name__}")
            min_tier = settings.get("min_tier")
            effects.append(
                EffectPolicy(
                    effect=str(name),
                    min_tier=Tier(int(min_tier)) if min_tier is not None else None,
                    caps=Caps.model_validate(settings.get("caps", {}) or {}),
                )
            )
        except (ValidationError, ValueError, TypeError) as exc:
            effect_refusals.append(
                Refusal(
                    stage=STAGE_EFFECTS,
                    message=f"effect '{name}': {_first_line(exc)}",
                    position=_position(root, ("effects", str(name))),
                )
            )
    if effect_refusals:
        return StagedResult(
            stopped_at=STAGE_EFFECTS,
            refusals=tuple(effect_refusals),
            policies=tuple(policies),
            effects=(),
        )

    return StagedResult(
        stopped_at=None,
        refusals=(),
        policies=tuple(policies),
        effects=tuple(effects),
    )


def _schema_message(loc: tuple[str | int, ...], msg: str) -> str:
    """Pydantic's message, prefixed by the field path it came from."""
    if not loc:
        return msg
    where = ".".join(str(part) for part in loc)
    return f"{where}: {msg}"


def _first_line(exc: Exception) -> str:
    """Pydantic errors are multi-line; a list row wants the reason, not the report."""
    text = str(exc).strip()
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if errors:
            loc = _loc_path(tuple(errors[0].get("loc", ())))
            return _schema_message(loc, str(errors[0].get("msg", "invalid")))
    return text.splitlines()[0] if text else exc.__class__.__name__
