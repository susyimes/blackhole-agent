# Skill Route Pass 1 Activation Readiness

Source digest: `github-growth-20260628T070730.472651Z`
Capability theme: `skill-route-discovery`
Pass: 1 of 4
Rollback artifact: `artifacts/rollback/20260628T070833Z-skill-route-discovery-pass1.md`
Rollback ref: `refs/blackhole-rollback/20260628T070833Z-skill-route-discovery-pass1`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with `SKILL.md`, repository resources, scripts, citation traceability, and explicit non-investment-advice boundary.
- `https://github.com/majidmanzarpour/threejs-game-skills`: director and specialist game skill bundle with QA, browser/canvas checks, scaffold helpers, and provider-backed asset boundaries.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem with clarification, repo-local task memory, handoff prompts, and collaboration profile state.

## Hypothesis

Pass-1 operators need a direct readiness panel for the active proposal IDs, not only prior pass fixtures. A body-free panel that maps each carried skill-route proposal to a selected local lane, source hashes, selected item IDs, validation gates, and denied activation actions improves replayability without granting upstream execution or local profile/memory writes.

## Change

- Added `current_run_pass1_activation_readiness` to the skill-route lane map and harness output.
- Added a local replay fixture for the active digest window.
- Added focused and aggregate harness regressions.
- Documented the new operator surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k current_run_pass1_activation_readiness`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k "current_run_pass1_activation_readiness or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery and pass1"`: passed, 6 tests.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k skill_route_discovery`: passed, 115 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

## Review Notes

- Self-model left unchanged: it already supports rollback-backed, locally validated behavior changes and does not need a policy rewrite for this evidence.
- The new panel is not an activation grant. Runtime action, upstream skill activation, external harness execution, provider launch, profile writes, memory writes, remote execution, raw evidence URLs, and upstream bodies remain denied.
