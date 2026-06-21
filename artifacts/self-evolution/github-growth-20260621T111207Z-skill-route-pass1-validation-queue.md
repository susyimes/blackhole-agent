# Skill Route Pass 1 Validation Queue

Source digest: `github-growth-20260621T111207.858584Z`
Capability theme: `skill-route-discovery`, pass 1 of 4
Rollback artifact: `artifacts/rollback/20260621T111206Z-skill-route-discovery-pass1.md`
Rollback ref: `refs/rollback/blackhole-agent/20260621T111206Z-skill-route-discovery-pass1`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and handoff/profile evidence should remain a bounded local state or documentation validation lane.
- `https://github.com/majidmanzarpour/threejs-game-skills`: game/frontend skill evidence should remain local frontend/test validation before any implementation lane.
- `https://github.com/baskduf/FableCodex`: Codex workflow gate evidence should prove `skill_route_discovery_first` before secondary workflow handling.
- `https://github.com/omnigent-ai/omnigent`: general-agent evidence is adjacent harness-eval pressure and should not inherit skill-route lanes.

## Hypothesis

The existing pass-1 handoff shows the next selected lane, but operators also need
the active anchoring proposals translated into replay rows. A body-free
`pass1_validation_queue` makes the proposal-to-lane mapping explicit and keeps
general-agent anchors gated outside skill-route discovery.

## Change

- Added `pass1_validation_queue` to `skill_route_discovery_lane` output.
- Updated the current-window pass-1 fixture to use this run's proposal IDs and
  Omnigent adjacency.
- Documented the queue contract in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "current_window_pass1 or pass1_exposes_current_action"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 20 tests.
- `python -m pytest tests/test_github_growth.py -q -k "skill_route or mixed_skill_workflow or route_activation_preflight"`: passed, 11 tests.

## Review Notes

The queue grants no runtime action and adds no allowed lanes. It cites selected
item IDs only and keeps raw source URLs, evidence URLs, target paths, and
upstream bodies out of the harness result.
