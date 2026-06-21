# Skill Route Discovery Pass 2 Profile Checklist

- Source digest: `github-growth-20260621T125209.784594Z`
- Capability theme: `skill-route-discovery`
- Prepared branch: `codex/blackhole-evolve/20260621T125331.633354-add-or-extend-local-skill-route-discovery-valida`
- Rollback ref: `refs/rollback/20260621T125209Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260621T125209Z-skill-route-discovery-pass2.txt`

## Evidence

- `https://github.com/baskduf/FableCodex`: mixed Codex/workflow/skill evidence that should prove `skill_route_discovery_first` before any workflow or harness gate.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state handoff evidence that should remain metadata/config bounded before profile or memory behavior.
- `https://github.com/majidmanzarpour/threejs-game-skills`: game frontend skill workflow evidence that should remain in local validation lanes before activation.
- `https://github.com/omnigent-ai/omnigent`: adjacent general-agent evidence, not a skill-route inheritance source.

## Hypothesis

The pass-2 lane already bounds public skill/workflow repositories to documentation,
config, test, and code_patch. The remaining local benefit is operator visibility:
`validation_readiness_summary` should show the per-profile acceptance contract
next to the selected current-pass lane so a supervisor can see which profiles are
selected now, which remain queued, and which bounded lane must be replayed before
activation.

## Change

- Added `profile_validation_checklist` to `skill_route_discovery_validation_readiness_summary`.
- The checklist mirrors the existing profile acceptance contract with body-free profile names, pass roles, expected first local lane, validation scope, gate name, metadata requirements, diagnostics, and replay commands.
- It keeps runtime action, external skill activation, external harness execution, provider launch, remote execution, raw source URL export, raw target path export, and upstream body export denied.
- Updated the focused pass-2 readiness regression and documentation contract.
- Left `docs/self-model.md` unchanged; its current preference for rollback-backed local evolution matched this behavior change and did not need revision.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls`
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls or skill_route_discovery_lane"`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`
- `python -m pytest tests/test_harness_eval.py tests/test_docs_contracts.py -q -k skill_route_discovery`

All validation commands passed.

## Review Notes

The checklist is a replay surface only. It does not inspect upstream skill
bodies, add local lanes, execute external repositories, or activate a secondary
harness. If a future pass wants to use queued COMPASS-style state handoff lanes,
it should still produce local config or metadata proof before activation.
