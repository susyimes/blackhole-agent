# Skill Route Discovery Pass 3: Route Profiles

Source digest: `github-growth-20260621T091208.050719Z`

Rollback ref:
`refs/blackhole-agent/rollback/20260621T091206Z/d1512fc6fb6235c3660e1ba9a2c99f30f415442a`

## Evidence

- `https://github.com/baskduf/FableCodex`: public Codex workflow/skill evidence with plugin, verification, tests, and eval signals.
- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem evidence with profile, handoff, and memory/state signals.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public domain skill evidence for Three.js/browser game workflows and QA.

## Hypothesis

The route classifier already keeps skill-like repositories inside documentation,
config, test, and code_patch lanes with `runtime_action: none`. Adding
body-free route profiles to the proposal evidence package makes pass-3 lane
selection more operator-visible: FableCodex-shaped evidence can be recognized
as a Codex workflow gate, COMPASS-shaped evidence as state/profile handoff, and
Three.js-shaped evidence as domain frontend workflow before any activation
decision.

## Changes

- Added `route_profiles` to skill/workflow route classification in
  `src/blackhole_agent/proposal_synthesis.py`.
- Carried route profiles through `route_classifier`,
  `skill_route_local_lane_candidates`, `mixed_skill_workflow_probe`, and
  `skill_route_boundary_report` surfaces.
- Added a regression covering FableCodex, COMPASS Skills, and Three.js Game
  Skills profile routing while preserving hashed source URLs and no runtime
  action.
- Updated `docs/skill-route-discovery.md` to document route-profile semantics.

The self-model was read and left unchanged. Its current preference already
matches this run: local evolution may proceed when rollback-backed, bounded,
validated, and outside the narrow safety boundary.

## Validation

- `python -m ruff check src\blackhole_agent\proposal_synthesis.py tests\test_github_growth.py`: passed.
- `python -m pytest tests/test_github_growth.py -q -k "skill_route_profiles or route_classifier_distinguishes or skill_route_local_lane_candidates or mixed_skill_workflow_probe"`: passed, 4 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "route_hint_lane_map or skill_route_discovery"`: passed, 5 tests.
- `python -m pytest tests/test_github_growth.py tests/test_proposal_eval.py -q -k "skill_route_discovery or mixed_skill_workflow or route_hint_lane_map or route_classifier or skill_route_local_lane_candidates"`: passed, 13 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or mixed_local_lane_probe"`: passed, 10 tests.

## Review Notes

- This pass does not install, enable, run, clone, or import upstream skill code.
- Raw upstream URLs are still hashed in operator route surfaces.
- Profiles are routing metadata only; local validation remains required before
  activation or secondary harness evaluation.
