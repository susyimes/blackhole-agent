# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260704T043308.886255Z`
- Theme: `skill-route-discovery`
- Rollback point: `artifacts/rollback/20260704T043307Z-skill-route-discovery-pass2/rollback-point.md`
- Self-model decision: left unchanged. The existing preference already supports rollback-backed, locally validated behavior changes and did not need a new category for this run.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package shape with `skills/reverse-flow`, local sandbox/CTF workflow framing, scripts, and upstream install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with source-cited workflow and advice-boundary metadata.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project without a local skill workflow route hint.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous/collaborative agent project without a local skill workflow route hint.

## Hypothesis

The active digest should expose an operator-visible pass-2 validation lane:
Codex and generic skill workflow evidence can become bounded local lanes, while
general-agent repositories remain adjacent `agent_harness_eval_required` rows
until a local harness result exists.

## Change

- Added the `github-growth-20260704T043308.886255Z` pass-2 selector in `src/blackhole_agent/skill_routing.py`.
- Added a frozen current-digest fixture at `tests/fixtures/skill_route_discovery/current_digest_20260704T043308_pass2_validation_lane.json`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Documented the operator replay path in `docs/skill-route-discovery.md`.

## Review Notes

- No upstream skill code was installed, cloned for execution, or run.
- Raw source URLs remain out of controller output; selected item IDs and hashes carry replay evidence.
- `reverse-flow-skill` install/runtime pressure is not exported as a selected local lane.
- Qwen-AgentWorld and Fundamental-Ava remain behind local harness evaluation.
