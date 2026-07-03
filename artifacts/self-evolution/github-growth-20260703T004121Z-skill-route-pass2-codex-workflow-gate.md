# Evolution Run: skill-route-discovery pass 2 Codex workflow gate

Source digest: `github-growth-20260703T004121.758638Z`
Branch: `codex/blackhole-evolve/20260703T004211.487041-add-or-extend-local-skill-route-discovery-valida`
Rollback artifact: `artifacts/self-evolution/github-growth-20260703T004121Z-rollback.md`
Rollback ref: `refs/blackhole-rollback/github-growth-20260703T004121Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: treated as bounded Codex/agent/skill/workflow evidence for `skill_route_discovery_first`.
- `https://github.com/lyra81604/zhengxi-views`: treated as generic/source-cited agent skill evidence for documentation-lane route discovery.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: treated as adjacent general-agent evidence requiring `agent_harness_eval_required`.

## Hypothesis

Pass-2 skill-route discovery should expose an operator-visible lane for Codex-oriented skill workflow evidence instead of falling back to the older generic/game/state pass-2 matrix. The lane should prove `skill_route_discovery_first`, keep local lanes bounded to documentation, config, test, and code_patch, and keep general-agent projects behind local harness evaluation.

## Changes

- Added current digest handling for `github-growth-20260703T004121.758638Z` in `current_digest_pass2_local_validation_lane`.
- Exported `route_probe_decisions` and `skill_route_discovery_first` on pass-2 skill-route rows.
- Added a frozen fixture for the active pass-2 evidence.
- Added regression coverage for the Codex workflow gate, generic skill workflow documentation lane, and adjacent agent harness boundary.
- Documented the pass-2 operator route in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260703T004121 or 20260702T214709_pass2 or 20260703T002121_pass1_reverse_flow_lane"`: passed, 3 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 191 tests.

## Review Notes

- No self-model change was made; the existing preference for validated local behavior change already matched this pass.
- No external activation, provider launch, external harness execution, remote execution, raw source URL export, raw evidence URL export, or upstream body export was added.
- The Codex gate row is anchored only to the reverse-flow candidate with `codex_workflow_gate`; zhengxi-views remains in the generic/source-cited documentation lane.
