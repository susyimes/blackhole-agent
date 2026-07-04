# Evolution Run: Skill Route Discovery Pass 3

- Source digest: `github-growth-20260704T073310.401263Z`
- Rollback point: `artifacts/rollback/20260704T073402Z-skill-route-discovery-pass3-current-window/rollback-point.md`
- Evidence reviewed: `https://github.com/lingbol088-spec/reverse-flow-skill`, `https://github.com/lyra81604/zhengxi-views`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`

## Hypothesis

Current pass-3 skill-route discovery should expose a source-digest-specific route-to-validation lane before activation. Codex-oriented reverse-flow skill workflow evidence and generic skill workflow evidence can enter bounded local validation lanes, while general agent projects without skill workflow hints must remain behind local agent-harness evaluation.

## Changes

- Added the `github-growth-20260704T073310.401263Z` branch in `current_digest_pass3_route_to_validation_lane`.
- Added a frozen current-digest fixture for reverse-flow, zhengxi-views, Qwen-AgentWorld, and Fundamental-Ava.
- Added a focused regression test covering bounded skill-route lanes, downgraded install/runtime pressure, local validation requirements, the pass-3 operator packet, and the adjacent general-agent harness gate.
- Documented the pass-3 route-to-validation behavior and replay command.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T073310`: passed, 1 test.

## Review Notes

- The self-model was read and left unchanged. Its current preference already matches this run: local evolution is acceptable when rollback-backed, validated, and explicit about uncertainty.
- Upstream install and runtime examples from reverse-flow remain diagnostic-only. No provider launch, external harness execution, remote execution, push, promotion, restart, profile write, or memory write was performed.
