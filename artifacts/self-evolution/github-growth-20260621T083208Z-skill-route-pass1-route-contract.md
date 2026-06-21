# Skill Route Discovery Pass 1 Route Contract

- Source digest: `github-growth-20260621T083208.222111Z`
- Capability theme: `skill-route-discovery`
- Pass: 1 of 4
- Branch: `codex/blackhole-evolve/20260621T083310.406074-add-or-extend-local-route-discovery-tests-for-re`
- Rollback ref: `refs/rollback/20260621T083206Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260621T083206Z-skill-route-discovery-pass1.txt`

## Evidence

The carried evidence URLs were treated as repository-level route evidence only:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/omnigent-ai/omnigent`

No upstream repository was cloned, installed, executed, or imported.

## Hypothesis

Skill/workflow repositories should continue to map only to bounded local
documentation, config, test, or code_patch lanes. General agent-project evidence
without a skill/workflow route signal should remain visible only through
`agent_harness_eval_required`, with `local_validation_required` explicit on the
operator-facing general-agent evaluation panel and each candidate row.

## Change

- Added `local_validation_required: true` to `general_agent_project_eval`
  candidate rows and the panel summary.
- Added a current-source replay test for the 2026-06-21T08:32Z pass-1 evidence
  mix: FableCodex, COMPASS Skills, and Three.js Game Skills stay in bounded
  `skill_workflow` route lanes; Omnigent stays in the general agent harness
  evaluation lane and does not inherit `skill_route_discovery`.
- Documented the general-agent validation-required contract in
  `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already supports this run's
  preference for rollback-backed, locally validated behavior changes over
  report-only updates.

## Validation

- `python -m ruff check src/blackhole_agent/proposal_synthesis.py tests/test_github_growth.py`
  passed.
- `python -m pytest tests/test_github_growth.py -q -k "current_skill_route_window or general_agent_project_eval_lane_requires_harness_evaluation_without_skill_lanes or route_activation_preflight_keeps_current_skill_window_bounded_before_activation or skill_route_local_lane_candidates_bound_current_skill_evidence_before_activation"`
  passed: 4 passed.
- `python -m pytest tests/test_github_growth.py -q -k "skill_route or route_classifier or general_agent_project or route_activation_preflight or route_hint_lane_map"`
  passed: 11 passed.
- `python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map or agent_harness_eval_fixture or omnigent"`
  passed: 9 passed.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane"`
  passed: 12 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
  passed: 2 passed.

## Review Notes

- The test uses body-free synthetic digest metadata and asserts that serialized
  route-map output does not export raw GitHub URLs.
- Mixed FableCodex-style evidence may preserve `agent_harness_eval` as an
  inferred secondary hint, but the primary route remains `skill_route_discovery`
  with only documentation, config, test, and code_patch lanes.
- General Omnigent-style evidence can infer `agent_harness_eval` from public
  agent-project text, but it does not inherit skill-route lanes or runtime
  action.
