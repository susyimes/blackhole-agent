# Skill Route Discovery Pass 4 Route Boundary

- Source digest: `github-growth-20260629T193904.337686Z`
- Capability theme: `skill-route-discovery`
- Pass: 4 of 4
- Branch: `codex/blackhole-evolve/20260629T193950.292193-add-or-extend-local-validation-coverage-for-skil`
- Rollback ref: `refs/rollback/blackhole-agent/20260629T193904Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback-20260629T193904Z-skill-route-discovery-pass4.md`

## Hypothesis

The final skill-route-discovery pass should leave an operator-visible boundary
checklist, not only another fixture. COMPASS Skills and zhengxi-views provide
skill workflow evidence that can enter bounded local skill-route lanes, while
Qwen-AgentWorld and looper are adjacent general-agent projects that must remain
behind `agent_harness_eval_required` before implementation.

## Change

- Added current digest `github-growth-20260629T193904.337686Z` handling to
  `current_digest_pass4_completion_handoff`.
- Added `route_boundary_checklist` to the handoff so skill workflow rows and
  general-agent rows are shown together with their route, lane, and denial
  booleans.
- Added a frozen current-digest fixture for COMPASS Skills, zhengxi-views,
  Qwen-AgentWorld, and looper.
- Added focused regression coverage for the current pass-4 route boundary.
- Documented the expected handling path in `docs/skill-route-discovery.md`.

## Material Actions

- Created rollback ref
  `refs/rollback/blackhole-agent/20260629T193904Z-skill-route-discovery-pass4`.
- Wrote rollback artifact
  `artifacts/rollback-20260629T193904Z-skill-route-discovery-pass4.md`.
- Edited local source, docs, and tests only.
- Did not restart the agent, promote the branch, push, install upstream code, or
  execute external repository code.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260629T193904_pass4_exposes_route_boundary"`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass4_completion_handoff or current_digest_pass4_completion_lane or 20260629T193904_pass4_exposes_route_boundary or 153904_pass4_completes_fixture_lane or 095324_pass4_completion_surface"`: passed, 5 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 110 tests.

## Review Notes

- The handoff remains body-free: raw upstream URLs, raw evidence URLs, target
  paths, replay commands, and upstream bodies are not exported.
- General-agent evidence can collect documentation, test, or code_patch harness
  evaluation outputs only after a local `agent_harness_eval` route exists; it
  does not inherit `skill_route_discovery`.
- The self-model was left unchanged because the existing preference for
  rollback-backed, locally validated behavior changes already covers this run.

