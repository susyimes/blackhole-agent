# Provider Runtime Control Pass 4

- Source digest: `github-growth-20260702T210709.499818Z`
- Capability theme: `provider-runtime-control`
- Rollback ref: `refs/blackhole-rollback/20260702T210708Z-provider-runtime-control-pass4`
- Rollback artifact: `artifacts/rollback/20260702T210708Z-provider-runtime-control-pass4.md`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: public repository shape includes `SKILL.md`, `skill.yml`, `evals`, `references`, and `scripts`; interpreted as a bounded `skill_route_discovery` candidate.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public repository is a general-agent project; interpreted as `agent_harness_eval_required`.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public repository is a general autonomous-agent project; interpreted as `agent_harness_eval_required`.
- `https://github.com/ksimback/looper`: public repository is a review-gated agent-loop project; interpreted as `agent_harness_eval_required`.

The Seedance workflow-only item is carried from the digest as a workflow-keyword boundary: without a skill-route hint or local harness result, it remains behind `agent_harness_eval_required`.

## Hypothesis

The final provider-runtime-control pass should expose an operator-visible lane-map checkpoint for the current digest. The checkpoint should complete the slice through local replay metadata only: bounded skill-route handoff, route-boundary checklist, recovery hint codes, and hashed replay commands, with provider launch and runtime action still denied.

## Change

- Added a source-digest route for `github-growth-20260702T210709.499818Z`.
- Added `provider_runtime_control_pass4_completion_checkpoint` to the pass-4 handoff for this digest.
- Added a frozen current-digest fixture and a focused regression test.
- Documented the pass-4 lane-map checkpoint in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260702T210709 or 20260702T204709"`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass4 or provider_runtime_control_pass3 or provider_runtime_control_pass2"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k "provider_runtime or skill_route_discovery"`: passed, 2 tests.

## Review Notes

- No provider was launched.
- No external harness was executed.
- No upstream body, raw evidence URL, provider value, preflight input, or replay command body is exported by the new checkpoint.
- The self-model was read and left unchanged because its current preference already matches this run: reversible local behavior changes are preferred when rollback-backed, validated, and outside the narrow safety boundary.
