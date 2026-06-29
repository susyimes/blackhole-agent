# Skill Route Discovery Pass 2 Local Validation Lane

Source digest: `github-growth-20260629T063941.864598Z`
Branch: `codex/blackhole-evolve/20260629T064039.352383-add-a-local-skill-route-discovery-validation-lan`
Rollback artifact: `artifacts/rollback/20260629T063940Z-skill-route-discovery-pass2.md`
Rollback ref: `refs/rollback/20260629T063940Z-skill-route-discovery-pass2`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/QwenLM/Qwen-AgentWorld/issues/2`

The reusable lesson is that skill-ecosystem and generic skill-workflow evidence
should become bounded local validation lanes before activation, while
general-agent benchmark evidence stays adjacent behind an agent-harness
evaluation probe.

## Hypothesis

If the current pass-2 lane adapts to the active evidence shape instead of
requiring an unrelated game/frontend profile, the operator surface can validate
the current COMPASS plus zhengxi-views slice directly while preserving the
existing denial boundary for Qwen-AgentWorld.

## Changes

- Added a profile-aware pass-2 spec path in `src/blackhole_agent/skill_routing.py`
  for COMPASS plus generic skill workflow evidence when no game/frontend
  profile is present.
- Added fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260629T063941_pass2_local_validation_lane.json`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Documented the pass-2 interpretation in `docs/skill-route-discovery.md`.

## Validation

- `pytest tests/test_skill_routing.py -q -k "20260629T063941 or pass2_focused_review_routes_active_proposals"`:
  passed, 2 tests.
- `pytest tests/test_skill_routing.py -q`: passed, 96 tests.
- `pytest tests/test_docs_contracts.py -q`: passed, 11 tests.

## Review Notes

- No upstream code was cloned, installed, or executed.
- Qwen-AgentWorld remains `agent_harness_eval_required`; it does not inherit
  `skill_route_discovery`, runtime execution, direct code_patch authority,
  provider launch, external harness execution, profile writes, memory writes,
  or remote execution.
- The self-model was read and left unchanged because it already matched the
  run evidence: prefer rollback-backed, locally validated behavior changes over
  report-only scaffolding.
