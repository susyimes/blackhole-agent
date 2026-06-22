# Skill Route Discovery Pass 1 Activation Targets

- Source digest: `github-growth-20260622T075431.644629Z`
- Branch: `codex/blackhole-evolve/20260622T075534.857357-add-or-extend-local-tests-for-bundled-agent-laun`
- Rollback artifact: `artifacts/rollback/20260622T075430Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260622T075430Z-skill-route-discovery-pass1`

## Evidence

The active window carried repository-level skill/workflow evidence from
FableCodex, COMPASS Skills, Three.js Game Skills, and Omnigent. The reusable
lesson for this pass is bounded route discovery: skill and workflow evidence
should become local documentation, config, test, or code_patch lanes only, with
an operator-visible validation target before any activation.

Omnigent-style provider or credential behavior remains review-only for this
pass because it crosses the privacy-leakage review boundary.

## Hypothesis

The existing lane map already exposes bounded lanes and profile gates, but a
supervisor still needs a compact activation-target panel that maps each
candidate profile to its selected local lane, replay command, and validation
target without exporting raw upstream bodies or granting runtime action.

## Change

- Added `local_activation_targets` to `build_skill_route_discovery_proposal_lane_map`.
- Each target row reports selected and queued bounded local lanes, route
  profiles, validation gates, a local validation target, focused replay command,
  source hash, first-route proof state, and activation blockers.
- Added focused assertions to the current-window skill-route fixture.
- Documented the panel in `docs/skill-route-discovery.md`.

No upstream code, install command, scaffold, provider route, browser check,
profile write, memory write, external harness execution, or remote execution
was adopted or run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "current_window_matrix or proposal_lane_map_bounds or game_frontend"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 63 tests.
- `python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py`: passed.

## Self-Model

`docs/self-model.md` was read and left unchanged. It remains a broad preference
statement rather than a behavior-shaping contract; the code and tests already
expressed the needed route-discovery boundary for this run.

## Review Notes

`local_activation_targets` is an operator handoff surface, not an activation
grant. Runtime action, upstream skill activation, external harness execution,
provider launch, remote execution, raw source URL export, raw evidence URL
export, and upstream body export remain denied.
