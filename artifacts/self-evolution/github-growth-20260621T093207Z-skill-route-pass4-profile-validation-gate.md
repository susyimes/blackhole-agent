# Skill Route Discovery Pass 4: Profile Validation Gate

Source digest: `github-growth-20260621T093207.753010Z`

Rollback ref: `refs/rollback/blackhole-agent/20260621T093206Z-skill-route-pass4-validation-gate`

Rollback artifact: `artifacts/rollback/20260621T093206Z-skill-route-pass4-validation-gate.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: public COMPASS Skills evidence shows a local skill ecosystem with task clarification, repo-local task memory, handoff prompts, collaboration profile state, and explicit local/privacy boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js game skill evidence shows browser game skill routing with QA, screenshots/canvas validation, scaffold boundaries, and optional asset/provider generation.
- `https://github.com/baskduf/FableCodex`: public FableCodex evidence shows a Codex-style workflow gate with local goal/findings ledgers and verification requirements.

No upstream skill code, installer, scaffold, browser checker, provider, asset generator, prompt body, or helper script was executed.

## Hypothesis

The pass-4 completion surface already checks required route-profile coverage, but final readiness is clearer and safer if the completion report also checks profile-specific validation lanes before supervisor handoff. Codex workflow evidence should still prove `skill_route_discovery_first`, game/frontend evidence should land on local test/frontend validation, and COMPASS-style state handoff evidence should land on local config/state-boundary validation.

## Changes

- Added `profile_validation_gate` to `skill_route_discovery_completion_report`.
- Added a top-level completion diagnostic for `codex_workflow_gate` when `skill_route_discovery_first` is not confirmed.
- Added regression coverage for the ready pass-4 gate and for blocking a Codex workflow profile that lacks the first-route proof.
- Documented the new gate in `docs/skill-route-discovery.md` and extended the docs contract.

The self-model was read and left unchanged. Its current preference already matches this run: proceed with rollback-backed, locally validated behavior changes outside the narrow safety boundary.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "codex_profile_without_first_route_gate or completion_report_surfaces_local_lane_closure or completion_accepts_required_profile_coverage"`: passed, 3 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 25 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "skill_route_discovery or route_hint_lane_map"`: passed, 5 tests.
- `python -m pytest tests/test_harness_eval.py -q`: passed, 119 tests.
- `python -m ruff check src\blackhole_agent\harness_eval.py tests\test_harness_eval.py tests\test_docs_contracts.py`: passed.
- `git diff --check`: passed with line-ending normalization warnings only.

## Review Notes

- The new gate is body-free. It records profile names, bounded lane names, validation scopes, metadata readiness, local artifact proof readiness, operator lane readiness, diagnostic hashes, and replay commands.
- It does not grant install, enable, run, execute, clone-and-run, scaffold, browser-checker, asset-generation, profile-write, memory-write, provider-launch, remote-execution, secondary harness execution, or external skill activation authority.
- External evidence remains repository-level routing evidence. Local validation remains required before activation or supervisor promotion.
