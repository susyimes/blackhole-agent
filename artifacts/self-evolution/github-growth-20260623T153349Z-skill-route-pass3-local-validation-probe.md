# Skill Route Discovery Pass 3 Local Validation Probe

Source digest: `github-growth-20260623T153349.021689Z`
Branch: `codex/blackhole-evolve/20260623T153500.559499-add-a-local-validation-probe-for-skill-ecosystem`
Rollback artifact: `artifacts/rollback/20260623T153500Z-skill-route-pass3-local-validation-probe.md`
Rollback ref: `refs/blackhole-rollback/20260623T153500Z-skill-route-pass3-local-validation-probe`

## Evidence

- `https://github.com/dongshuyan/compass-skills` presents COMPASS as a local skill ecosystem for task clarification, repo-local task memory, handoff prompts, and local collaboration profile work.
- `https://github.com/baskduf/FableCodex` is Codex/workflow-shaped evidence that should keep `skill_route_discovery_first` before any broader workflow or harness lane.
- `https://github.com/majidmanzarpour/threejs-game-skills` is game/frontend skill evidence that should remain in a local test/frontend validation lane before any activation.

## Hypothesis

Pass-3 skill-route discovery already has bounded lane selection, profile gates, proof summaries, checkpoints, and a runbook. The missing operator surface is a single local validation probe that ties route profiles to the selected bounded local lane, validation gate, selected item IDs, hashed source evidence, queue fingerprint, and activation denials before final-pass activation review.

## Change

- Added `pass3_handoff_packet.local_validation_probe`.
- The probe maps `codex_workflow_gate`, `game_frontend_workflow`, and `skill_ecosystem_state_handoff` to bounded local lanes and fails closed when the acceptance contract, local artifact proof, first-route decision, or promotion runbook step is not ready.
- The probe exports selected item IDs and hashed source identifiers only. It denies runtime action, external skill activation, external harness execution, provider launch, remote execution, raw evidence URL export, raw source URL export, raw target path export, and upstream body export.
- Documented the new pass-3 probe in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile or skill_route_discovery_pass3_blocks_when_profile_contract_is_not_ready"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed.
- `python -m compileall -q src/blackhole_agent`: passed.

## Review Notes

- The selected local `test` lane intentionally groups FableCodex-style workflow-gate evidence with game/frontend skill evidence. The probe preserves that grouped queue fingerprint and candidate-source hash set instead of pretending the selected test queue is per-source.
- The self-model was read and left unchanged. Its current preference for rollback-backed, locally validated behavior matched this run; no new evidence showed it was misleading.
