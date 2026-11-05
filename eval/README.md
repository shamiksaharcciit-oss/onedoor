# onedoor eval

A scripted, rerunnable evaluation of onedoor against scenarios built from a
published challenge's own failure modes for irreversible autonomous actions.
No model and no network: every scenario's actions are fixed data, and the
"agent" proposing them is the script itself, so a run gives the same numbers
every time.

## What it measures

Every scenario is a short script of proposed actions, each carrying its own
ground truth (`harmful` or `legitimate`) and a one-line reason the label is
right. Each scenario runs twice: once against a plain executor that carries
out everything a script proposes, and once through onedoor's own decision
API. The comparison gives four numbers, per category and in total:

- **harmful actions carried out**, without onedoor and with it;
- **legitimate actions wrongly stopped**, with onedoor;
- **actions held for a person**, kept separate from stopped, since a human
  still deciding is not the same as a denial;
- **duplicate effects** (the tool-failure category only): the same effect
  carried out twice, when a retry was not correlated to the attempt it
  retried.

Eight categories, at least four scenarios each, mixing harmful and
legitimate actions (`ordinary_work` is legitimate throughout, by design --
it is the baseline a wrongly-stopped action would show against):
`ambiguity`, `conflicting_constraints`, `tool_failure`, `permits`,
`injected_instruction`, `approval`, `kill_switch`, `ordinary_work`.

The written results (`RESULTS.md`) are produced by the runner, never by
hand. Anywhere onedoor's actual decision did not match a scenario's ground
truth -- a harmful action carried out, a legitimate one wrongly stopped, a
duplicate effect, or an expired approval that re-proposed instead of
resolving denied -- is recorded as a finding (`FINDINGS.md`), alongside
which roadmap item would address it. Nothing here changes onedoor itself:
findings are kept, not fixed.

## Running it

From a fresh venv with this repository's own `[dev]` extra installed:

```
pip install -e ".[dev,service]"
python -m eval run
```

Add `--only CATEGORY` to run one category alone (one of the eight names
above), and `--record` to additionally record and verify every "with
onedoor" run with onetrace (an optional extra; see the recording section
further down). Each run writes `eval/RESULTS.md` and `eval/FINDINGS.md` at
the repository root.

## Adding a scenario

Add a file under `eval/scenarios/`, matching the existing ones' shape: a
`name`, a `category` (one of the eight above), a plain-words `description`,
and an `actions` list. Each action needs an `action_type`, its `params`, a
`ground_truth` (`harmful` or `legitimate`), and a `why`. An action type needs
a policy somewhere it will be loaded from: the shipped payments pack
(`onedoor/templates/payments/policies.yaml`) or this evaluation's own extra
policies (`eval/policies/eval_extra.yaml`) -- add a policy there if the
scenario needs an action type neither already declares. A scenario that
scripts a retry, an approval answer, a kill-switch state, or a permit's
shape uses the optional fields `retry_of`, `approve`, `kill_switch`,
`permit`, `approval_ref_from` and `wait_seconds` -- see
`eval/harness/scenario.py` for exactly what each one does.

## What this doesn't show

These scenarios are scripted: the "agent" is fixed data, not a model, so
this measures how onedoor decides on the actions these scenarios describe,
not how any particular model or framework would behave when it is the one
doing the describing. onedoor decides on an action as it is described to
it -- a mis-described or wrongly mapped action is decided as described, and
that is true here exactly as it is true of onedoor itself. A finding here
is a property of these scenarios against this version of onedoor; it is not
a claim about every agent or every tool.
