# Skill Route Discovery Pass 3: Current Action Surface

Source digest: `github-growth-20260620T211207.809970Z`

Capability window: `skill-route-discovery`, pass 3 of 4.

## Evidence Reviewed

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`

The evidence still supports local validation lanes only. FableCodex is useful
as workflow-gate evidence, COMPASS Skills as state-handoff and routing metadata
evidence, and Three.js Game Skills as domain-director validation evidence. No
upstream code, install command, scaffold, profile store, or runtime action was
adopted.

## Hypothesis

The pass-3 harness already selects bounded per-profile validation lanes, but the
next supervisor action was buried in nested panels. Lifting the selected target
into a compact top-level `current_action` row should make the continuation path
operator-visible without widening the route beyond documentation, config, test,
or code_patch lanes.

## Rollback

Rollback artifact: `artifacts/rollback/20260620T211206Z-skill-route-discovery-pass3.txt`

Rollback ref: `refs/rollback/skill-route-discovery-pass3-20260620T211206Z`

## Changed Files

- `src/blackhole_agent/harness_eval.py`
- `tests/test_harness_eval.py`
- `tests/test_docs_contracts.py`
- `docs/skill-route-discovery.md`
- `artifacts/rollback/20260620T211206Z-skill-route-discovery-pass3.txt`

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile or skill_route_discovery_lane"`
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_bounded_matrix`
- `pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map or agent_harness_eval_fixture"`
- `pytest tests/test_skill_routing.py -q`

All commands passed.

## Review Notes

- `current_action` is derived from `validation_lane_plan.next_validation_target`.
- It exports selected item IDs and candidate source hashes, not raw source URLs
  or upstream bodies.
- It repeats denials for runtime action, external skill activation, external
  skill code, external harness execution, provider launch, remote execution, raw
  evidence URL export, raw source URL export, raw target path export, and
  upstream body export.
- The self-model was read and left unchanged because the existing preference
  already supports this rollback-backed local behavior improvement.
