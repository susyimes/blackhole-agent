# Runner Harness Control Pass 2

Source digest: `github-growth-20260706T191555.447457Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill` is a Codex-oriented skill workflow signal. It supports bounded skill-route discovery, but the local lesson remains classification and validation rather than installing or running upstream skill code.
- `https://github.com/shepherd-agents/shepherd` presents reversible, retained agent execution traces and reportable run outputs. The reusable lesson for this pass is an operator-visible runner workflow surface: intake, mid-flight state, recovery, replay, and report artifacts should be inspectable end to end.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava` remain general agent-project evidence. They support `agent_harness_eval_required` style intake, not direct runtime activation.

## Hypothesis

The existing `agent_workflow_route` control-plane fixture is useful, but pass 2 should make the handoff easier to replay. A stage-order contract and typed artifact manifest let an operator verify that a runner workflow is complete without reading raw URLs, commands, paths, report bodies, or provider output.

## Change

- Added `stage_order_contract` to the `workflow_handoff` packet.
- Added `artifact_manifest` rows for source intake, state transition trace, rollback/recovery handoff, local replay fixture, and operator report.
- Extended the pass-2 fixture and focused regression test to assert the new handoff fields.
- Updated architecture documentation for the expanded control-plane contract.

## Rollback

Rollback point:

- `refs/blackhole-rollback/20260707T000000Z-runner-harness-control-pass2`
- `artifacts/rollback/20260707T000000Z-runner-harness-control-pass2/rollback-point.md`
- `artifacts/rollback/20260707T000000Z-runner-harness-control-pass2/rollback-point.json`

Recovery remains explicit:

```powershell
git switch codex/blackhole-evolve/20260706T191647.107527-run-a-bounded-skill-route-discovery-lane-for-the
git reset --hard refs/blackhole-rollback/20260707T000000Z-runner-harness-control-pass2
git clean -fd
```

## Validation

Focused validation:

```powershell
pytest tests/test_harness_eval.py -q -k agent_workflow_route_control_plane
# 1 passed, 244 deselected

pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs
# 1 passed, 244 deselected

ruff check src\blackhole_agent\harness_eval.py tests\test_harness_eval.py
# All checks passed
```

## Review Notes

- Self-model unchanged. It already says reversible, locally validated behavior changes are preferred over report-only work, and this run did not produce new evidence that should alter that self-description.
- No upstream repository code, skill files, runtime provider, or external harness was installed or executed.
- Supervisor-controlled commit, promotion, push, and restart remain outside this kernel run.
