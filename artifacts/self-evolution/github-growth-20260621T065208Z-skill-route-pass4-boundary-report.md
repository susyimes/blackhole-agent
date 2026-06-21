# Skill Route Discovery Pass 4 Boundary Report

- Source digest: `github-growth-20260621T065208.198099Z`
- Capability window: `skill-route-discovery`, pass 4 of 4
- Branch: `codex/blackhole-evolve/20260621T065416.244544-add-a-local-skill-route-discovery-validation-lan`
- Rollback artifact: `artifacts/rollback/20260621T065208Z-skill-route-discovery-pass4.txt`
- Rollback ref: `refs/rollback/20260621T065208Z-skill-route-discovery-pass4`

## Hypothesis

The final pass should expose an operator-visible boundary summary at the
route-hint lane-map layer. Public skill/workflow repositories such as
FableCodex, COMPASS Skills, and Three.js Game Skills should remain in bounded
`skill_route_discovery` lanes, while general agent repositories such as
Omnigent and xuefeng-agent should require `agent_harness_eval_required` and not
inherit skill-route lanes.

## Change

- Added `skill_route_boundary_report` to `build_route_hint_lane_map`.
- The report records skill workflow rows, general agent project rows, mixed
  skill/workflow counts, allowed local lanes, required local validation, and
  denial flags.
- Skill rows keep `primary_route: skill_route_discovery` with documentation,
  config, test, or code_patch lanes only.
- General agent rows keep `primary_route: agent_harness_eval_required` with
  documentation, test, or code_patch evaluation lanes and
  `skill_route_discovery_inherited: false`.
- Mixed FableCodex-style rows keep
  `agent_harness_eval_after_local_corroboration` blocked until local
  corroboration.
- Updated the skill-route documentation and docs contract test.

## Validation

- `pytest tests/test_github_growth.py -q -k "skill_route_boundary_report or general_agent_project_eval_lane or mixed_skill_workflow"`:
  passed, 3 tests.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records`:
  passed, 2 tests.
- `pytest tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_github_growth.py -q -k "skill_route_discovery or mixed_skill_workflow or route_hint_lane_map or agent_harness_eval or skill_route_boundary_report"`:
  passed, 28 tests.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane or completion_report"`:
  passed, 13 tests.

## Review Notes

The report is metadata-only. It exports selected item IDs and source URL hashes,
not raw source URLs or upstream bodies. It adds no proposal lanes, runs no
external harness, launches no provider, performs no remote execution, activates
no external agent, and activates no upstream skill code.

The self-model was read and left unchanged. Its current preference already
matches this run: make rollback-backed, locally validated behavior improvements
when evidence and validation coverage justify them.
