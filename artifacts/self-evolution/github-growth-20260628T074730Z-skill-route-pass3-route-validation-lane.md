# Skill Route Discovery Pass 3 Route Validation Lane

- Source digest: `github-growth-20260628T074730.300165Z`
- Branch: `codex/blackhole-evolve/20260628T074843.462240-add-a-local-skill-route-discovery-validation-lan`
- Rollback artifact: `artifacts/rollback/20260628T074843Z-skill-route-discovery-pass3-local-lane.md`
- Rollback ref: `refs/rollback/20260628T074843Z-skill-route-discovery-pass3-local-lane`

## Hypothesis

The active skill-route-discovery pass needs an operator-visible route validation
lane keyed to the current proposal IDs, not only historical pass-3 surfaces.
The lane should reuse existing local activation proof machinery, map Three.js
game skill evidence to a local test lane, and make the
`skill_ecosystem_state_handoff` input/output boundary explicit before any
activation path.

## Local Change

- Added `current_pass3_route_validation_lane` to the proposal lane map.
- Reused `current_active_pass3_local_activation_proof_lane` as the source proof.
- Rekeyed rows to:
  - `p1-skill-route-discovery-generic`
  - `p2-threejs-game-skill-routing`
  - `p3-skill-ecosystem-state-handoff`
- Added body-free route IO contracts and state-handoff boundary metadata.
- Documented the lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_pass3_route_validation_lane`
  - Result: passed, 1 passed and 69 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
  - Result: passed, 2 passed and 9 deselected.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, 70 passed.

## Review Notes

This lane remains classification and replay metadata only. It exports proposal
IDs, selected item IDs, route profiles, source hashes, bounded lane names,
validation tasks, and body-free IO contracts. It keeps runtime action, upstream
skill activation, external harness execution, provider launch, profile writes,
memory writes, remote execution, raw source URLs, raw evidence URLs, target
paths, replay-command bodies, and upstream bodies denied.

The self-model was read and left unchanged because its current preference
already supports rollback-backed, locally validated behavior changes and does
not need to become the improvement artifact for this run.
