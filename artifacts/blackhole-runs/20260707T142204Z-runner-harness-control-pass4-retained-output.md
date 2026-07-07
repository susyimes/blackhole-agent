# Runner Harness Control Pass 4: Retained Output Selection

## Changed Files

- `src/blackhole_agent/harness_eval.py`
- `tests/test_harness_eval.py`
- `tests/fixtures/local_harness_eval/agent_workflow_route_retained_output_selection.json`
- `artifacts/blackhole-runs/20260707T142204Z-runner-harness-control-pass4-retained-output.md`
- `artifacts/rollback/20260707T142204Z-runner-harness-control-pass4/rollback-point.md`
- `artifacts/rollback/20260707T142204Z-runner-harness-control-pass4/rollback-point.json`

## Evidence And Hypothesis

- Source digest: `github-growth-20260707T142109.485817Z`
- Capability theme: `runner-harness-control`, pass 4 of 4.
- Evidence reviewed narrowly: `https://github.com/shepherd-agents/shepherd`
- Reusable lesson: Shepherd treats agent work as retained, inspectable output that can be reviewed before selection or discard. That maps to a local runner-harness control-plane contract without running Shepherd or granting external execution.
- Hypothesis: `agent_workflow_route` should expose whether runner outputs are retained, inspectable, settleable, and blocked from activation until operator selection.

## Validation

- `python -m py_compile src/blackhole_agent/harness_eval.py`
- `python -m pytest tests/test_harness_eval.py -q -k "agent_workflow_route_retained_output_selection or unsettled_retained_outputs or local_harness_eval_runs_pass"`: 2 passed, 251 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k "retained_output_selection or unsettled_retained_outputs"`: 2 passed, 251 deselected.
- `python -m pytest tests/test_harness_eval.py -q`: 253 passed.

## Rollback

- Rollback ref: `refs/rollback/20260707T142204Z-runner-harness-control-pass4`
- Rollback artifact: `artifacts/rollback/20260707T142204Z-runner-harness-control-pass4/rollback-point.md`
- Recovery remains explicit and destructive; no rollback command was executed in this run.

## Replay

- Replay fixture: `tests/fixtures/local_harness_eval/agent_workflow_route_retained_output_selection.json`
- Focused replay command: `python -m pytest tests/test_harness_eval.py -q -k "retained_output_selection or unsettled_retained_outputs"`

## Review Notes

- No upstream code was cloned, installed, or run.
- Raw evidence URLs, recovery commands, output IDs, changeset refs, and private marker strings are not exported by the evaluated harness output.
- Self-model left unchanged: its current preference already supports rollback-backed, locally validated runtime and harness improvements; this run added behavior rather than a new self-description.
