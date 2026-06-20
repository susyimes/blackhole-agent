# Self-Evolution Run Notes

Source digest: `github-growth-20260620T153207.694032Z`
Branch: `codex/blackhole-evolve/20260620T153306.436185-add-or-extend-a-local-skill-route-discovery-vali`
Rollback artifact: `artifacts/rollback/20260620T153306Z-provider-runtime-control-pass2.md`
Rollback ref: `refs/rollback/blackhole-agent/20260620T153306Z`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem with local `SKILL.md` workflows, install language, local state/profile boundaries, and validation notes.
- `https://github.com/baskduf/FableCodex`: Codex workflow-gate plugin with evidence, inspection, review, and verification habits.
- `https://github.com/majidmanzarpour/threejs-game-skills`: agent skill bundle for Three.js game workflows with installer and QA/helper language.

No upstream skill code, installer, scaffold, browser checker, provider, prompt body, or asset generator was executed.

## Hypothesis

The skill-route lane already bounds public skill/workflow evidence to documentation, config, test, or code_patch lanes. For the active `provider-runtime-control` capability window, the more useful pass-2 improvement is to require a locally replayable provider/runtime preflight sample before the completion surface can continue, while keeping diagnostics body-free and recovery explicit.

## Change

- Added `provider_runtime_sample_gate` to `skill_route_discovery_capability_window_completion`.
- Provider-runtime-control windows, or windows that explicitly request provider-runtime sample coverage, now block with `provider_runtime_preflight_sample_missing` when `provider_runtime_preflight_samples` are absent.
- Ready samples allow non-final windows to remain `in_progress`; blocked samples keep routing through existing provider-runtime recovery hints.
- Completion recovery now maps missing provider-runtime samples to local preflight replay commands.
- Updated `docs/skill-route-discovery.md` and focused harness regressions.

## Self-Model

Read `docs/self-model.md` before choosing the patch. It already frames rollback-backed local evolution and provider/config preflight checks as valid growth paths while leaving permissions to runtime policy, so it was left unchanged.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass or skill_route_discovery_pass2_fixture"` passed: 3 passed, 103 deselected.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or provider_runtime_recovery_summary"` passed: 10 passed, 96 deselected.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed: 2 passed, 6 deselected.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery` passed: 17 passed, 25 deselected.

## Review Notes

- This change does not install, enable, run, execute, clone, scaffold, generate assets, launch providers, perform remote execution, push, promote, or restart.
- The new gate exports only booleans, counts, status labels, failure classes, hashes already used by surrounding surfaces, and replay commands.
- Skill-route-only capability windows keep provider-runtime samples optional unless they explicitly opt into the provider-runtime-control contract.
