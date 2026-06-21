# Skill Route Discovery Pass 3 Validation Work Queue

Source digest: `github-growth-20260621T075207.956135Z`
Capability theme: `skill-route-discovery`
Pass: `3 of 4`
Branch: `codex/blackhole-evolve/20260621T075336.035346-run-a-bounded-local-skill-route-discovery-evalua`
Rollback ref: `refs/rollback/20260621T075207Z-skill-route-discovery-pass3`
Rollback artifact: `artifacts/rollback/20260621T075207Z-skill-route-discovery-pass3.md`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`: public SKILL.md ecosystem with task clarification, repo-local task memory, handoff prompts, local collaboration profile state, install/manual-copy instructions, and explicit local/privacy boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public game-oriented skill repository for Three.js browser game workflows and validation-oriented specialist routing.
- `https://github.com/baskduf/FableCodex`: public Codex-style workflow evidence for gated review, verification, and skill/workflow routing.

No upstream skill code, installer, scaffold, browser checker, provider, asset generator, prompt body, or helper script was executed.

## Hypothesis

The pass-3 skill-route lane already selects bounded local lanes and carries queued lanes forward. It is more useful to operators if the harness also emits a validation work queue that joins each selected route profile to candidate-level evidence and local artifact targets, while preserving the existing no-runtime-action and body-free boundaries.

## Change

- Added `validation_work_queue` to `skill_route_discovery_lane` output.
- Added `skill_route_discovery_validation_work_queue()` and `skill_route_discovery_validation_work_step()` in `src/blackhole_agent/harness_eval.py`.
- The queue maps FableCodex and Three.js Game Skills profiles to local `test` work items, and COMPASS state-handoff profile to a local `config` work item.
- Rows expose selected item IDs, hashed candidate identifiers, hashed candidate source identifiers, hashed local artifact targets, replay commands, and supervisor replay steps.
- Rows deny runtime action, external skill activation, external skill code, external harness execution, provider launch, remote execution, raw evidence URL export, raw source URL export, raw target path export, and upstream body export.
- Extended the pass-3 harness regression and documented the queue in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_pass3_selects_bounded_lane_per_profile`: passed, 1 passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 passed.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 19 passed.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 56 passed.

## Review Notes

- Self-model was read and left unchanged. Its current preference for rollback-backed, locally validated behavior matches this run.
- The queue is an operator-visible local replay surface, not activation authority.
- External evidence remains repository-level. It justifies local queue metadata and regression coverage, not installing or executing upstream skill packages.
