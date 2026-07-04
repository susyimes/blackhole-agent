# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260704T041308.895594Z`
- Theme: `skill-route-discovery`
- Rollback point: `artifacts/rollback/20260704T041409Z-skill-route-discovery-pass1-current-digest/rollback-point.md`
- Self-model decision: left unchanged. The existing preference already supports rollback-backed, locally validated behavior changes and did not need a new category for this run.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package shape with `skills/reverse-flow`, local sandbox/CTF workflow framing, scripts, and install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with source-cited workflow and advice-boundary metadata.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project without a local skill workflow route hint.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous/collaborative agent project without a local skill workflow route hint.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow/usecase collection without a reusable local skill package or local harness result.

## Hypothesis

The active digest should produce an operator-visible pass-1 validation lane:
Codex/skill workflow repositories can enter bounded local lanes only after local validation, while general-agent and workflow-usecase repositories remain in `agent_harness_eval_required` before any implementation route.

## Change

- Added the `github-growth-20260704T041308.895594Z` pass-1 selector in `src/blackhole_agent/skill_routing.py`.
- Added a frozen current-digest fixture at `tests/fixtures/skill_route_discovery/current_digest_20260704T041308_pass1_validation_lane.json`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Documented the operator replay path in `docs/skill-route-discovery.md`.

## Review Notes

- No upstream skill code was installed, cloned for execution, or run.
- Raw source URLs remain out of controller output; selected item IDs and hashes carry replay evidence.
- `reverse-flow-skill` install/runtime pressure is treated as diagnostic only.
- Qwen-AgentWorld, Fundamental-Ava, and workflow/usecase evidence remain behind local harness evaluation.
