# Provider Runtime Control Pass 3

Source digest: `github-growth-20260702T204709.437283Z`

## Evidence

- `https://github.com/lyra81604/zhengxi-views` exposes Agent Skill packaging signals (`SKILL.md`, `skill.yml`, references, scripts, evals) and scheduled workflow language, so it remains bounded `skill_route_discovery` evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper` are general agent/eval/loop projects without an explicit skill route signal in this pass.
- Workflow-only Seedance usecase evidence is treated as `agent_harness_eval_required` documentation triage, not runtime workflow adoption.

## Hypothesis

Pass 3 of `provider-runtime-control` should make the recovery path operator-visible: current skill-route and adjacent agent evidence should produce body-free recovery hints and local replay command hashes while denying provider launch, external harness execution, remote execution, and runtime action.

## Change

- Dispatch the current digest to the existing provider-runtime pass-3 preflight lane.
- Add `provider_runtime_control_pass3_operator_recovery_workflow` to summarize current pass, next pass, blocked proposals, recovery hint codes, and replay command hashes.
- Add current-digest fixtures for direct skill routing and local harness replay.
- Document the pass-3 rule in `docs/upstream-evidence-interpretation.md`.

## Rollback

Rollback artifact: `artifacts/rollback/20260702T204708Z-provider-runtime-control-pass3.md`

Rollback ref: `refs/rollback/blackhole-agent/provider-runtime-control-pass3-20260702T204708Z`

## Validation

Passed:

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T204709` -> 1 passed, 183 deselected
- `python -m pytest tests/test_harness_eval.py -q -k "20260702T204709 or local_harness_eval_runs_pass"` -> 1 passed, 224 deselected
- `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q` -> 409 passed

## Review Notes

- No self-model edit was made; the current self-model already supports rollback-backed local evolution with a narrow safety boundary, and this run did not reveal a more behavior-shaping self-description.
- No provider, external harness, remote runner, or upstream code was executed.
