# Evolution Run: Provider Runtime Control Pass 1

Source digest: github-growth-20260702T140627.665756Z
Capability theme: provider-runtime-control
Branch: codex/blackhole-evolve/20260702T140844.606994-add-or-extend-local-tests-for-skill-route-discov
Rollback ref: refs/blackhole-rollback/20260702T140844-provider-runtime-control-pass1
Rollback note: artifacts/rollback-20260702T140844Z-provider-runtime-control-pass1.md

## Evidence Reviewed

- https://github.com/lyra81604/zhengxi-views: explicit Agent Skill packaging and workflow language; usable as bounded skill-route evidence, not external activation.
- https://github.com/QwenLM/Qwen-AgentWorld: general agent-project evidence; remains adjacent harness-eval material.
- https://github.com/TianhangZhuzth/Fundamental-Ava: general autonomous-agent evidence; remains adjacent harness-eval material.
- https://github.com/ksimback/looper: review-gated agent loop evidence; supports replay/checklist treatment rather than direct runtime activation.

## Hypothesis

The route-classification fixtures already cover the p1 and p2 boundaries. The higher-benefit pass-1 improvement is to make provider-runtime recovery replay more operator-visible by adding a compact, body-free `operator_recovery_plan` to the existing `recovery_replay_packet`.

## Change

- Added `skill_route_discovery_provider_runtime_recovery_packet_plan`.
- Included `operator_recovery_plan` in provider-runtime recovery replay packets for blocked, review, ready, and not-applicable statuses.
- Extended focused tests for missing-sample and degraded-sample provider-runtime recovery paths.
- Updated `docs/skill-route-discovery.md` to describe the nested replay plan.

## Safety Boundary

No provider launch, remote execution, external skill activation, raw provider values, raw diagnostics, raw preflight inputs, raw upstream bodies, or raw evidence URLs are exported by the new plan.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_provider_runtime_control_pass_requires_replay_sample or skill_route_discovery_provider_runtime_control_pass_surfaces_degraded_recovery_packet"`: passed
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed

## Self-Model

`docs/self-model.md` was left unchanged. It already treats provider/config preflight and validated local behavior as valid evolution targets, and this run did not contradict or refine that preference.
