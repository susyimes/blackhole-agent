# Skill Route Pass 2 Preactivation Checklist

Source digest: `github-growth-20260628T124729.646401Z`
Branch: `codex/blackhole-evolve/20260628T124819.265405-add-or-extend-local-route-discovery-tests-that-a`
Rollback artifact: `artifacts/rollback/20260628T124728Z-skill-route-discovery-pass2.md`
Rollback ref: `refs/rollback/20260628T124728Z-skill-route-discovery-pass2`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state-handoff shaped evidence.
- `https://github.com/lyra81604/zhengxi-views`: generic source-cited skill workflow evidence.
- `https://github.com/majidmanzarpour/threejs-game-skills`: browser game frontend skill workflow evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent benchmark evidence, kept in `agent_harness_eval_required`.

## Hypothesis

Pass 2 already preserves route hints, route profiles, bounded lanes, and adjacent
agent-eval separation. The useful next improvement is an operator-visible
preactivation checklist that derives replay steps from those classifications
without exporting raw upstream URLs, raw replay commands, or any activation
authority.

## Change

- Added `preactivation_checklist` to `current_pass2_validation_lane`.
- The checklist records skill-route rows and adjacent agent-harness rows as
  body-free replay items with hashed source or command references.
- Skill-route rows remain limited to documentation, config, test, and code_patch
  lanes.
- Adjacent general-agent evidence stays in `agent_harness_eval_required` and does
  not inherit `skill_route_discovery`.
- Provider launch, remote execution, external harness execution, external agent
  activation, and external skill activation remain denied.
- Updated route documentation to name the pass-2 checklist as a replay/review
  surface rather than activation authority.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_pass2_validation_lane_keeps_agent_eval_adjacent`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 66 tests.

## Review Notes

- Self-model was read and left unchanged. It already matches this run: direct,
  rollback-backed, locally validated behavior is preferred over another
  standalone validation report.
- No runtime execution, external harness launch, provider launch, promotion,
  push, restart, profile write, or memory write was performed.
- Raw upstream URLs are present only in source fixtures and this run artifact;
  the new checklist exports hashes instead.
