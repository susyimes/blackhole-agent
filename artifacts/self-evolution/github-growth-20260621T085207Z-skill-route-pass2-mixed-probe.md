# Skill Route Discovery Pass 2

Source digest: `github-growth-20260621T085207.833962Z`

Branch: `codex/blackhole-evolve/20260621T085309.084950-add-or-extend-local-tests-that-exercise-skill-ro`

Rollback ref: `refs/rollback/blackhole-agent/20260621T085404Z-skill-route-discovery-pass2`

Rollback artifact: `artifacts/rollback/20260621T085404Z-skill-route-discovery-pass2.md`

## Evidence

- `https://github.com/baskduf/FableCodex`: public repository presents a Codex plugin/skill workflow with examples, tests/evals, evidence gates, and local ledgers.
- `https://github.com/dongshuyan/compass-skills`: public repository presents multiple local skills, including task clarification, repo-local task memory, session handoff, and collaboration profile state.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public repository presents a domain skill pack with director/specialist skills, installers, scaffold helpers, browser QA, and optional provider-backed generation.

No upstream code, installer, scaffold, helper script, provider probe, or skill body was imported or executed.

## Hypothesis

FableCodex-shaped evidence can be mixed Codex/skill/workflow evidence even when the word `agent` is absent from the selected summary. The core disabled-registry lane map should route that shape through `skill_route_discovery_first` before broader harness evaluation, while preserving the stronger `agent` term as an audit flag rather than a prerequisite.

## Change

- Relaxed the core mixed-probe predicate from Codex+workflow+skill+agent to Codex+workflow+skill.
- Added `full_mixed_signal` to candidate inventory and proposal-lane rows so operator surfaces can distinguish rows that also mention `agent` or `agents`.
- Added a FableCodex-shaped regression that omits the agent term and still selects `skill_route_discovery_first` with only documentation, config, test, and code_patch lanes.
- Updated the skill-route discovery documentation and docs contract for the new route rule.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference for rollback-backed, locally validated behavior changes matches this run, and no evidence from this pass showed that the file is shaping runtime behavior or needs a new category.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "mixed_codex or skill_route_discovery_proposal_lane_map_bounds_recognized_skill_evidence"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 25 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or mixed_local_lane_probe or pass2_handoff"`: passed, 10 tests.
- `python -m pytest tests/test_github_growth.py -q -k "mixed_skill_workflow or skill_route_boundary_report or route_activation_preflight"`: passed, 3 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map"`: passed, 5 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "mixed_codex_workflow_skill or mixed_codex_agent_workflow"`: passed, 2 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py tests/test_docs_contracts.py`: passed.

## Review Notes

The change adds no allowed lanes and grants no runtime action. Secondary harness evaluation remains blocked until local corroboration or a general agent-project claim exists. COMPASS-style memory/profile evidence and Three.js installer/scaffold/provider evidence remain bounded to local documentation, config, test, or code_patch validation lanes.
