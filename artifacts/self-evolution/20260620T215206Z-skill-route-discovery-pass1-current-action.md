# Skill Route Discovery Pass 1 Current Action

- Source digest: `github-growth-20260620T215207.776951Z`
- Capability window: `skill-route-discovery`, pass 1 of 4
- Rollback ref: `refs/rollback/20260620T215206Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260620T215206Z-skill-route-discovery-pass1.txt`

## Evidence

- `dongshuyan/compass-skills` presents a multi-skill local state and handoff system with task clarification, task memory, session handoff, and local profile signals.
- `majidmanzarpour/threejs-game-skills` presents a domain director and specialist skill bundle with QA, browser/game validation, scaffold, provider, and asset-generation signals.
- `baskduf/FableCodex` presents mixed Codex, plugin, skill, workflow-gate, evidence-ledger, examples, tests, and verification signals.

These are routing lessons, not activation authority. No upstream code, installer, scaffold, provider launch, credential probe, or skill body was imported or executed.

## Hypothesis

A pass-1 skill-route window should expose the first concrete local validation lane through `current_action` when `next_validation_target` is ready, even if broader catalog or handoff surfaces remain review-labeled. This lets the supervisor continue the bounded local validation lane without inferring a target from raw repository URLs or README claims.

## Local Change

- Updated `skill_route_discovery_current_action` to mark the action ready when the selected `next_validation_target` is ready and the lane plan has no diagnostics.
- Added `skill_route_discovery_lane_pass1_current_action.json` as a replay fixture for the current pass-one evidence mix.
- Added regression coverage that verifies the selected local lane is `test`, raw source URLs are not exported, runtime action is `none`, and external skill activation remains denied.
- Documented that pass-one windows use the same `current_action` handoff and that mixed Codex/workflow/skill evidence remains `skill_route_discovery_first`.

## Validation

```bash
pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass1_exposes_current_action_for_mixed_skill_routes or local_harness_eval_runs_pass_and_fail_fixtures"
pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane
pytest tests/test_skill_routing.py -q -k skill_route_discovery
pytest tests/test_docs_contracts.py -q -k skill_route_discovery
pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_docs_contracts.py -q
```

All listed validation passed in this run.

## Review Notes

- The self-model was read and left unchanged. It already permits rollback-backed local evolution and did not need a new behavioral claim.
- `capability_window_completion` can remain blocked on pass 1 while `current_action` is ready. Completion readiness is stricter than next-lane selection and still requires final-pass handoff conditions.
- The new fixture is body-free and keeps public repository URLs out of harness output.
