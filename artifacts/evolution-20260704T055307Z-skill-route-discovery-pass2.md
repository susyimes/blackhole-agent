# Evolution Run: skill-route-discovery pass 2

- Source digest: `github-growth-20260704T055309.687829Z`
- Branch: `codex/blackhole-evolve/20260704T055407.677347-evaluate-the-codex-oriented-reverse-flow-skill-r`
- Rollback artifact: `artifacts/rollback/20260704T055307Z-skill-route-discovery-pass2/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260704T055307Z-skill-route-discovery-pass2`
- Self-model: read and left unchanged. The current self-model already supports rollback-backed, locally validated local evolution; this run had stronger evidence for an operator-visible pass-2 route lane than for revising self-description text.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted as Codex/AI-agent reverse-flow skill evidence with skill package layout, workflow framing, and install/runtime pressure. That pressure remains diagnostic only.
- `https://github.com/lyra81604/zhengxi-views`: interpreted as generic/source-cited Agent Skill workflow evidence suitable for a documentation lane.
- `https://github.com/QwenLM/Qwen-AgentWorld`: interpreted as adjacent general-agent harness evidence; fork or trend activity can raise review interest but does not bypass local harness evaluation.

## Hypothesis

The active pass-2 slice should expose a digest-specific local validation lane for `github-growth-20260704T055309.687829Z` instead of relying on the previous pass-1 lane or stale pass-2 proposal IDs. Codex workflow-gated skill evidence should route only to documentation, config, test, or code_patch lanes before activation, while adjacent general-agent projects remain in `agent_harness_eval_required` with explicit pre-eval empty lanes.

## Changes

- Added current digest handling to `skill_routing.py` for the `20260704T055309` pass-2 lane.
- Added explicit `direct_allowed_lanes_before_eval: []` and `allowed_local_lanes_after_eval` fields to pass-2 adjacent agent rows.
- Added a frozen fixture for the active pass-2 source digest.
- Added a regression test proving the Codex workflow gate, generic skill route, and adjacent agent harness rows stay bounded and body-free.
- Documented the new replay surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T055309`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T043308 or 20260704T053309 or 20260704T055309"`: passed, 3 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 249 tests.

## Review Notes

- No runtime action, provider launch, external skill activation, external harness execution, remote execution, profile write, memory write, raw source URL export, raw replay command export, or upstream body export is enabled.
- Qwen-AgentWorld and Fundamental-Ava remain adjacent harness-eval rows only. They may inform documentation, test, or code_patch work only after local harness evaluation succeeds.
