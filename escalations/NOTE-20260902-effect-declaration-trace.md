# Delivery → Core — Note: the effect-declaration trace (R083 §4)

**Date:** 2026-09-02 · **From:** delivery channel (onedoor) · **To:** core
**Answering:** `Core_to_Delivery_Response_083_2026-09-02.md` §4, restated live by
`Core_to_Delivery_Response_084_2026-09-02.md` §2.
**Method:** read-only, zero spend, no live calls. One local database built and discarded.

---

## The answer

**Nothing on the path refuses it.** The silent filter at `decision.py:219` runs against a
policy set that can, and does, contain a rule naming an effect absent from
`effect_policies`. Every gate between Studio submission and that line accepts such a rule.

**It is a live-engine gap, and it is already ruled: this is `ND-053`**, raised by this
channel, ruled by **R049 §6**, deliberately frozen because the fix is breaking. It needs
no new severity read to be *discovered*; §5 below gives the read R084 asked for anyway.

---

## 1. The path, link by link

| Link | Lines | Refuses a rule naming an undeclared effect? |
|---|---|---|
| `policy_loader.validate_policy` — boot, fail-closed | **31–102** | **No.** Eight `raise ValueError` sites (**35, 44, 54, 67, 75, 85, 90, 98**); none reads `policy.effects` at all |
| `validate.problems` — the Studio's validator | **65–86** | **No.** Calls `validate_policy` at **83**, and discards the effects it was handed at **79**: `_ = effects` |
| `staging.staged` — upload, editor, API | — | **No.** A wrapper over the two above; it adds stages, not rules |
| `ratify.ratify` — the ceremony | **325–376** | **No.** Its only `RatificationRefused` is at **351** (the version compare-and-swap). Effects appear at **333** (parameter), **363** (`_apply`) and **370** (`diff_effects`) — carried and diffed, never checked against the rules that name them |
| `policy_loader.upsert` / `upsert_effect` / `load_file` | — | **No** |
| `decision.py` | **219** | **No** — `effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]` drops the unmatched effect silently |

`validate.problems`'s line 79 is the sharpest single citation. The function **receives**
the candidate's effects and explicitly discards them, with a docstring saying why: effect
policies have no `validate_policy` of their own, so checking them here would be a second
validator. That reasoning is sound for what the function is — and it means the one place
in the Studio that sees rules and effects together looks at neither in relation to the
other.

## 2. Proven, not concluded from reading

A rule at Tier 2 naming `money.egress`, taken through the real path twice — once with the
effect policy declared, once without. Same rule, same request, same engine:

```
effect declared=False  ->  PermittedIntent   effective_tier=2                        (executes)
effect declared=True   ->  ActionResult      decision=proposed  effective_tier=3
                                             reason=effect_floor  requires_approval=True
```

On the way in, for the undeclared case: `validate_policy` returned cleanly, the Studio's
validator reported `[]`, and the ceremony ratified it.

**The same request auto-executes without the effect policy and goes to a human with it.**
The protection is not weakened by the missing declaration; it is absent.

## 3. This is `ND-053`, and it is core's own ruling

> **`validate_policy` refuses an effect label with no `effect_policies` row behind it.**
> Ruled by R049 §6 on delivery's escalation: the label is silently dropped today, so the
> same request is `PERMITTED, effective_tier 1` with it alone and `proposed,
> effective_tier 3` once the effect policy exists — *a protection that depends on a
> second, optional declaration is not a protection.* **Breaking**, its own release, **no
> opt-out flag** (a switch permitting inert effects is the law applied to its own escape
> hatch), and the refusal names the effect, the rule and the remedy. Detector shipped in
> `ND-052`/S4 so operators can find every instance first. — **specced, unbuilt**

The trace reproduces that ruling's own worked example, at Tier 2 rather than Tier 1. So
the finding is not new; what is new is a second, independent confirmation of it from the
decision path rather than from the loader, and a line citation for each link.

## 4. Where it *is* visible today

Detected in three surfaces, refused in none:

- `coverage.DECLARED_INERT` — the map ranks it **first** in `PROMINENCE`, because
  *declared but inert* sounds fine and behaves dangerously.
- `forecast.build` — `ND-056`/T1's second list forecasts `effect_floor` for it, naming the
  reason code that will *not* speak.
- `benchmark.check` — scores it as a miss, which is how the live model's compliance with
  an adversarial "declare it later" request was caught.

That is what "detector shipped so operators can find every instance first" looks like in
the code, and `0.7.0` adds the second of the three.

## 5. The severity read R084 asked for before Sept 8

**Real, bounded, and not newly urgent.**

- **What it costs.** An effect floor that an operator believes is governing does not
  govern. The failure direction is permissive: the action executes where it should have
  gone to a human.
- **What it takes to happen.** An operator must ratify a policy that names an effect they
  never declared. It is an authoring error on a human-ratified artifact, not an
  attacker-reachable path: nothing an agent sends can create one, and the Studio shows it
  in two places before ratification.
- **What is already true.** Known since R049 (2026-08-24), ticketed, specced, with a
  detector shipped ahead of the fix precisely so instances can be found first.
- **Does it bear on the tag?** **No.** `0.7.0` is Studio-only and additive; it neither
  introduces nor worsens this. If anything it improves detection, since T1's forecast list
  surfaces the case a third way. Holding the tag for a frozen, known, breaking fix would
  spend launch week on a fact the register has had for nine days.
- **When it should land.** Unchanged: the post-launch line with `ND-054`, as ruled. The
  fix is breaking and the freeze is the reason it waits, not an oversight.

**Delivery proposes nothing new.** The ruling stands as made; this note supplies the
citations and the second confirmation, and nothing here argues for re-opening it.

## 6. One genuine discrepancy this surfaced, unfixed

`benchmark.check`'s docstring says *"Every rule checked here is one the engine also
enforces."* Given §1, that is **true of the engine's intended contract and false of the
shipped one**: the scorer enforces the named-effect law today; the engine will when
`ND-053` lands.

A small honesty defect in prose, in the same scorer whose false-pass fix R083 §2 queued to
the T3-for-`0.7.1` design. **Not touched** — it is an instrument-of-the-gate edit, it
changes no number, and correcting it mid-freeze on delivery's own authority is the move
this channel keeps declining. Queued beside the other scorer work.

Integrity: sha256(body) = 15b4aaae96ce5a5a7bb3d9e5df0186edfb19eb1a6e6cbce3c99611d6cf274abb
