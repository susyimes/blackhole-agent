# Blackhole Run: skill-route-discovery pass 1 local validation lane

Source digest: `github-growth-20260708T175850.390217Z`
Branch: `codex/blackhole-evolve/20260708T175940.152314-create-a-bounded-local-validation-lane-for-codex`
Rollback ref: `refs/rollback/20260709T020000Z-skill-route-discovery-pass1-local-validation-lane`
Rollback artifact: `artifacts/rollback/20260709T020000Z-skill-route-discovery-pass1-local-validation-lane/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` is a Codex/AI Agent reverse-flow skill package with local sandbox/CTF framing, staged workflow, scripts, and install/run examples.
- `Pluviobyte/rnskill` is a generic SKILL.md-compatible skills collection with skills, docs, tools, and plugin/marketplace metadata.
- `shepherd-agents/shepherd` is a reversible agent runtime substrate with permissions, retained outputs, replay, and credential/runtime setup pressure.
- `Tencent-Hunyuan/Hy3` is a reasoning/agent model project with API, deployment, provider, and model-serving pressure.

## Hypothesis

The current pass-1 window should preserve the active proposal IDs while routing only skill/workflow candidates to bounded local lanes. Reverse-flow belongs in the local test lane, rnskill belongs in the documentation lane, and Shepherd/Hy3 must remain adjacent `agent_harness_eval_required` rows with no direct runtime, provider, permission, promotion, or restart authority.

## Changes

- Added the `github-growth-20260708T175850.390217Z` specialization to the pass-1 validation lane.
- Added a local harness fixture and focused regression for the current digest.
- Documented the operator-visible acceptance contract in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already expresses the local validated evolution preference used by this run and grants no permissions.

## Validation

Passed:

- `python -m pytest tests/test_harness_eval.py -q -k 20260708T175850`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`

## Review Notes

- Discovery remains body-free and strips install/run/provider/runtime/external-harness pressure.
- Raw source URLs, evidence URLs, replay commands, target paths, and upstream bodies remain out of the lane output.
- Activation, promotion, push, restart, provider launch, and remote execution remain supervisor/operator concerns, not outputs of this pass.
