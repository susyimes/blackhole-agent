# Skill Route Discovery Current Window Pass 1

- Source digest: `github-growth-20260621T043207.872197Z`
- Capability theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260621T043313.869904-add-or-extend-local-skill-route-discovery-tests-`
- Rollback artifact: `artifacts/rollback/20260621T043207Z-skill-route-discovery-pass1-current-run.txt`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/ACN1987/FableCodex`
- `https://github.com/baskduf/FableCodex`

COMPASS exposes a local skill ecosystem with task clarification, task memory,
handoff, and profile-state boundaries. Three.js Game Skills exposes
domain-specific browser-game skill routing with QA and asset/provider
boundaries. FableCodex exposes mixed Codex, agent, skill, and workflow language
that should enter `skill_route_discovery` before broader harness evaluation.

## Hypothesis

The active pass should have a replayable current-window lane using the exact
carried proposal IDs and evidence sources, not only older pass fixtures. A
ready pass-1 handoff should select bounded local validation, preserve hashed
lineage for FableCodex mirrors, and keep the secondary harness lane blocked
until local corroboration exists.

## Change

- Added `skill_route_discovery_lane_current_window_pass1.json` as a local
  harness fixture for the current source digest.
- Added a focused regression asserting selected item IDs, current action,
  FableCodex mixed-route ordering, hashed mirror lineage, and activation
  denials.
- Updated the aggregate local-harness fixture count.
- Documented the current pass-1 replay contract in
  `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or current_window_pass1"`:
  passed, 10 passed.

## Review Notes

- No upstream skill bodies, installers, scaffolds, browser helpers, provider
  routes, external harnesses, or profile/memory writes were imported or run.
- The self-model was read and left unchanged because it already describes the
  preference for rollback-backed local evolution with explicit uncertainty.
