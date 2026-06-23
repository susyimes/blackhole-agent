# Skill Route Discovery Pass 2 Proposal Validation Catalog

Source digest: `github-growth-20260623T151348.984839Z`

Rollback artifact: `artifacts/rollback/20260623T151348Z-skill-route-discovery-pass2.md`

Rollback ref: `refs/blackhole-rollback/20260623T151348Z-skill-route-discovery-pass2`

## Evidence

The active capability window carried skill/workflow repository evidence from
FableCodex, COMPASS Skills, zhengxi-views, and Three.js game skills. The local
pass-2 fixture already models those repositories as bounded skill-route
discovery candidates, each limited to documentation, config, test, and
code_patch lanes.

## Hypothesis

Future pass-2 activation review is clearer if the harness exposes a
proposal-lane catalog before activation. Grouping all current-window candidates
by local proposal lane lets an operator verify that documentation, config, test,
and code_patch work are the only available lanes while runtime-shaped actions
remain downgraded, blocked, and non-executable.

## Change

- Added `proposal_validation_lane_catalog` to `skill_route_discovery_lane`
  output.
- The catalog groups candidates by documentation, config, test, and code_patch,
  exports selected item IDs plus hashed candidate/source identifiers, and
  reports unsupported lane and blocked-action counts.
- The catalog keeps `runtime_action: none` and denies external skill
  activation, external harness execution, provider launch, remote execution,
  and raw source/evidence/body export.
- Documented the operator-facing surface in `docs/skill-route-discovery.md`.

## Validation

Passed:

- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff or skill_route_discovery_lane"`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`

## Review Notes

The self-model was read and left unchanged. It already describes this run's
preference for rollback-backed, locally validated behavior changes and did not
need a new behavior-shaping claim.
