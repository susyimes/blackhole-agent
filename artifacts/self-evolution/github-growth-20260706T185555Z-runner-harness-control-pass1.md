# Runner Harness Control Pass 1

Source digest: `github-growth-20260706T185555.435343Z`

Capability window: `runner-harness-control`, pass 1 of 4.

## Evidence

Carried proposal evidence:

- `https://github.com/InternScience/Agents-A1`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/shepherd-agents/shepherd`

The digest framed these as general agent or harness projects. The local lesson
used here is not to import upstream runtime behavior, but to make one existing
runner workflow legible end to end: intake, mid-flight state, recovery, replay,
and report artifacts.

## Hypothesis

The existing `agent_workflow_route` control plane already records lifecycle,
rollback, report sections, and operator replay metadata. However, the replay
stage could be marked ready for the `runner-harness-control-plane` gate when
validation checks existed but no replay artifact path was recorded. Requiring a
body-free replay artifact for that gate makes the operator handoff more
replayable without enabling external harness execution or provider launch.

## Change

- `src/blackhole_agent/harness_eval.py`
  - Requires `replay_path` for the `runner-harness-control-plane` replay stage.
  - Exposes `replay_artifact_required` and `replay_artifact_recorded` booleans.
  - Adds `replay_artifact_missing` diagnostics and an operator checklist action:
    `record_replay_artifact_before_operator_replay`.
- `tests/test_harness_eval.py`
  - Verifies passing control-plane fixtures report replay artifact readiness.
  - Adds a missing replay artifact regression that blocks only the replay stage
    and keeps raw rollback refs out of serialized output.

## Rollback

Rollback artifact:
`artifacts/rollback/20260706T185554Z-runner-harness-control-pass1/rollback-point.md`

Rollback ref:
`refs/rollback/20260706T185554Z-runner-harness-control-pass1`

Rollback execution is explicit operator policy only.

## Validation

- `pytest tests/test_harness_eval.py -q -k agent_workflow_route`
  - Result: 9 passed, 236 deselected.
- `pytest tests/test_harness_eval.py -q`
  - Result: 245 passed.

## Review Notes

- Self-model reviewed and left unchanged. Its current preference for direct,
  rollback-backed local behavior improvements matches this run.
- No upstream code was run, cloned, installed, or activated.
- No provider launch, external harness execution, remote execution, promotion,
  push, or restart path was added.
- The new requirement is scoped to the `runner-harness-control-plane` gate so
  older non-control-plane workflow fixtures remain valid.
