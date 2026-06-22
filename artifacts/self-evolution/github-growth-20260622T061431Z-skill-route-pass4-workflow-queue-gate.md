# Skill Route Discovery Pass 4 Workflow Queue Gate

- Source digest: `github-growth-20260622T061431.444321Z`
- Capability theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260622T061535.558903-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/blackhole-rollback/20260622T061430Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260622T061430Z-skill-route-discovery-pass4.txt`

## Evidence

The current window carried FableCodex, COMPASS Skills, and Three.js Game Skills
as bounded skill/workflow evidence. A focused review of the cited repositories
confirmed the same shape used by the digest: FableCodex presents Codex workflow
gates and verification habits, while the skill repositories are external skill
bundles. The local lesson is to keep the final operator queue explicit that
mixed Codex/workflow evidence must pass through `skill_route_discovery_first`
before any broader workflow lane can be considered ready.

## Hypothesis

The pass-4 completion report is more replayable if `route_validation_lane_queue`
surfaces a per-row workflow gate. The queue should show that
`skill_route_discovery_first` is confirmed for FableCodex-style workflow rows
and should block that queued row if the first-route proof is absent, while still
denying runtime action, external skill activation, external harness execution,
provider launch, remote execution, and raw upstream evidence export.

## Changes

- Added `workflow_gate` to each `skill_route_discovery_route_validation_lane_queue`
  row.
- Added a queue diagnostic:
  `skill_route_discovery_first_not_confirmed_before_workflow_gate`.
- Extended pass-4 ready and blocked tests for the queue gate.
- Documented the queue-level workflow gate in `docs/skill-route-discovery.md`.

The self-model was left unchanged. Its existing preference for rollback-backed,
locally validated behavior changes already matched this run, and no new
behavior-shaping self-description was needed.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "completion_report_surfaces_local_lane_closure or codex_first_route_gate"`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_harness_eval.py -q -k completion_blocks_codex_profile_without_first_route_gate`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 22 tests.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_docs_contracts.py -q -k "skill_route_discovery or completion_blocks_codex_profile_without_first_route_gate"`: passed, 61 tests.

## Review Notes

- No external repository code was installed, cloned, executed, imported, or used
  as an activation source.
- The queue gate is body-free and records only bounded local decisions and
  diagnostics.
- Repository activity remains non-authoritative movement pressure; it does not
  grant activation or runtime permission.
