# Skill Route Validation Profile Coverage

- Source digest: `github-growth-20260623T033653.556282Z`
- Capability theme: `upstream-evidence-capability`
- Selected proposal: `p1-skill-route-discovery-registry`
- Rollback ref: `refs/blackhole-rollback/20260623T033651Z`
- Rollback artifact: `artifacts/rollback/20260623T033651Z-rollback.md`

## Evidence

The carried evidence names public skill/workflow repositories:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`

No broad trend discovery was rerun. The local reusable lesson is that skill and
workflow signals should become an operator-visible bounded validation surface,
not upstream skill activation.

## Hypothesis

Adding a first-class `validation_profile_coverage` report to
`build_skill_route_discovery_proposal_lane_map` makes pass-3 skill-route
coverage inspectable for `skill_term`, `mixed_skill_workflow_probe`,
`generic_skill_workflow`, `skill_ecosystem_state_handoff`,
`game_frontend_workflow`, and `codex_workflow_gate` while preserving the
allowed local lanes: documentation, config, test, and code_patch.

## Changes

- Added `SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES`.
- Added `validation_profile_coverage` to the source-registry proposal lane map.
- Added a focused regression covering all six requested profile shapes and
  asserting bounded lanes, local validation, and denied runtime/external action.
- Documented the new report in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already matches the run policy:
  local evolution is allowed when rollback-backed, validated, and outside the
  narrow safety boundary.

## Validation

- `python -m pytest tests/test_skill_routing.py -q`: passed, 31 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`:
  passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`:
  passed, 9 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`:
  passed.
- `python -m compileall -q src\blackhole_agent\skill_routing.py`: passed.

## Review Notes

- The new report is metadata-only and body-free. It hashes candidate sources,
  denies raw source URL and upstream body export, and does not grant runtime
  action, provider launch, external harness execution, remote execution, or
  external skill activation.
- `zhengxi-views` remains covered by the existing source-cited domain research
  route profile; this pass focused on the six profiles named by the active
  proposal.
