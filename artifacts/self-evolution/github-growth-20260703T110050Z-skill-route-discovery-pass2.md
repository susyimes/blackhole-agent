# Skill Route Discovery Pass 2

Source digest: `github-growth-20260703T110050.082761Z`

Rollback point: `artifacts/rollback/20260703T110145Z-skill-route-discovery-pass2/rollback-point.json`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/reverse-flow/SKILL.md`, local sandbox/CTF workflow framing, scripts, and install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation behavior, and an investment-advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/world-model project without skill workflow evidence in the selected digest.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous/social-agent project without skill workflow evidence in the selected digest.

## Hypothesis

Pass 2 should expose both skill-like workflow items as bounded local `skill_route_discovery` lanes before activation, while keeping Qwen-AgentWorld and Fundamental-Ava as adjacent `agent_harness_eval_required` rows until a concrete local harness fixture exists.

## Local Change

- Added a current-digest local harness fixture for `github-growth-20260703T110050.082761Z`.
- Extended the pass-2 lane selector so the active digest emits:
  - `p1-skill-route-discovery-codex-workflow-gate` for reverse-flow-skill.
  - `p2-generic-skill-workflow-route-discovery` for zhengxi-views.
- Added a regression test asserting Qwen-AgentWorld and Fundamental-Ava remain blocked behind `agent_harness_eval_required` with no inherited skill-route lane, external harness execution, provider runtime launch, or remote execution.

## Validation

- `uv run pytest tests/test_harness_eval.py::test_skill_route_discovery_current_digest_20260703T110050_pass2_validation_lane -q`
- `uv run pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q`
- `uv run pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `uv run pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`

All validation commands passed.

## Review Notes

The self-model was read and left unchanged. It already permits rollback-backed local evolution while keeping runtime policy external, and this run did not uncover evidence that the file currently shapes route behavior.

No upstream code was installed, imported, executed, or cloned. Raw GitHub source URLs and upstream bodies remain absent from the local harness output.
