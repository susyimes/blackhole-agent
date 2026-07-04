# Skill Route Discovery Pass 3 Current Digest

- Source digest: `github-growth-20260704T102435.124198Z`
- Branch: `codex/blackhole-evolve/20260704T102534.489489-add-or-extend-local-skill-route-discovery-tests-`
- Rollback ref: `refs/rollback/20260704T102637Z-skill-route-discovery-pass3-current-digest`
- Rollback artifact: `artifacts/rollback/20260704T102637Z-skill-route-discovery-pass3-current-digest/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public AI Agent/Codex skill workflow with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, scripts, and install/runtime examples. Local lesson: route through `skill_route_discovery_first`, keep only bounded local lanes, and downgrade install/runtime pressure to diagnostics.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill workflow with source-cited research/eval signals. Local lesson: generic skill workflow evidence can enter a test validation lane with `runtime_action: none`.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: general-agent projects without skill workflow hints in this digest. Local lesson: keep them in `agent_harness_eval_required` and review-only before any implementation route.

## Hypothesis

The current pass-3 window needs an operator-visible route-to-validation lane for the active proposal IDs. It should prove Codex-oriented skill workflow candidates start with `skill_route_discovery_first`, generic agent+skill workflow evidence remains bounded by local validation, and general-agent projects do not inherit skill-route lanes.

## Change

- Added a frozen current-digest fixture for `github-growth-20260704T102435.124198Z`.
- Extended the pass-3 route-to-validation mapper to recognize the current digest and emit:
  - `p1-skill-route-discovery-codex-workflow`
  - `p2-generic-skill-workflow-lane-coverage`
  - `p3-agent-harness-eval-for-general-agent-projects`
- Added regression coverage that asserts bounded lanes, no raw evidence URL export, no runtime action, no provider launch, no external skill/harness activation, and no direct general-agent implementation lane before local harness evaluation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260704T102435"`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T102435 or 20260704T100436 or 20260704T094434 or 20260704T085309"`: passed, 4 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass3_route_to_validation or 20260704T102435"`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 261 tests.

## Self-Model

`docs/self-model.md` was left unchanged. Its current preference already matches this run: direct local behavior improvement under rollback and validation, with only offensive behavior, abuse, unauthorized access, and privacy leakage kept review-only.

## Review Notes

- `reverse-flow-skill` is security-adjacent reverse-analysis evidence, so this run treats it as local skill-route validation only and does not install, execute, clone-and-run, or activate upstream code.
- General-agent projects remain review-only through `agent_harness_eval_required`; no direct runtime, provider, remote execution, or code patch lane is inferred from their trend evidence.
