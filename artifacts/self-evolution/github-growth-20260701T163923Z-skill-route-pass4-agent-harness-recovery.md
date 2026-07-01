# Skill Route Discovery Pass 4 Agent Harness Recovery

- Source digest: `github-growth-20260701T163923.124908Z`
- Theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260701T164035.723556-create-a-bounded-local-skill-route-discovery-val`
- Rollback artifact: `artifacts/rollback/20260701T163921Z-skill-route-discovery-pass4-agent-harness-recovery.md`
- Rollback ref: `refs/blackhole-rollback/skill-route-discovery-pass4-agent-harness-recovery`

## Evidence

- `https://github.com/lyra81604/zhengxi-views` exposes skill-shaped repository metadata: `SKILL.md`, `skill.yml`, references, evals, scripts, source citation requirements, and a non-investment-advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava` remain general-agent project evidence rather than local skill-package evidence.
- `https://github.com/ksimback/looper` is carried as adjacent general-agent workflow evidence in the digest window.

## Hypothesis

Pass 4 should leave the supervisor with a recovery workflow for adjacent general-agent rows, not just a blocked gate. A body-free recovery packet can say what local probe fields, claim mappings, queue state, and replay command are needed before documentation, test, or code_patch follow-up lanes are allowed.

## Change

- Added `agent_harness_eval_recovery_workflow` to `agent_harness_eval_implementation_readiness_contract`.
- The workflow records global blockers, per-project next steps, allowed follow-up lanes after recovery, and the local replay command.
- The workflow keeps runtime action, external agent activation, external harness execution, provider launch, remote execution, raw source URL export, and upstream body export denied.
- Added focused regression assertions for the current Qwen-AgentWorld/Fundamental-Ava/looper trend fixture.
- Documented the pass-4 recovery surface in `docs/skill-route-discovery.md`.

## Validation Plan

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_current_digest_trending_projects_stay_local_validation_required`
- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_current_digest_20260701T153922_pass1_local_validation_lane`
- `pytest tests/test_harness_eval.py -q`
- `pytest -q`

## Validation Result

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_current_digest_trending_projects_stay_local_validation_required`: 1 passed.
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_current_digest_20260701T153922_pass1_local_validation_lane`: 1 passed.
- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: 3 passed.
- `pytest tests/test_harness_eval.py -q`: 204 passed.
- `pytest -q`: 581 passed.

## Review Notes

- No upstream code was cloned, installed, or executed.
- No provider runtime was launched.
- The self-model was read and left unchanged because its current preference for validated local behavior over report-only artifacts matched the selected change.
