# Skill Route Discovery Pass 2 Handoff Metadata

Source digest: `github-growth-20260622T053431.406906Z`
Branch: `codex/blackhole-evolve/20260622T053540.325051-add-or-strengthen-local-validation-for-skill-rou`
Rollback artifact: `artifacts/rollback/20260622T053430Z-skill-route-discovery-pass2.txt`
Rollback ref: `refs/blackhole-rollback/20260622T053430Z-skill-route-discovery-pass2`

## Evidence

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/omnigent-ai/omnigent`

The current capability window is pass 2 of 4 for converting skill and route
evidence into bounded local lanes that can be validated before activation.

## Hypothesis

Skill-route discovery is more useful to the operator if the core lane map
exposes explicit handoff metadata before downstream pass packets interpret it.
The metadata should select one bounded local validation lane, queue remaining
bounded lanes, cite profile validation gates, require local validation, and keep
runtime action and external activation denied.

## Change

- Added `handoff_metadata` to every core skill-route candidate inventory row and
  proposal-lane row.
- Threaded sanitized handoff metadata into the harness `candidate_lane_intake`
  panel for operator-visible pass-2 review.
- Documented the new core handoff field in `docs/skill-route-discovery.md`.
- Added focused regression assertions in route-map and pass-2 harness tests.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`
  passed: 18 passed, 9 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_pass2_fixture`
  passed: 1 passed, 119 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
  passed: 9 passed, 111 deselected.
- `python -m ruff check src/blackhole_agent/skill_routing.py src/blackhole_agent/harness_eval.py tests/test_skill_routing.py tests/test_harness_eval.py`
  passed.

## Review Notes

- Self-model was read and left unchanged. Its current preference already covers
  rollback-backed local evolution and did not need a new behavioral claim.
- No upstream code, install scripts, prompts, or skill bodies were imported or
  executed.
- The change preserves manual repository mode and read-only digest mode:
  handoff metadata is local, body-free, and bounded to documentation, config,
  test, or code_patch lanes.
