# Skill Route Pass 3 Operator Checkpoints

Source digest: `github-growth-20260621T063208.123051Z`
Capability theme: `skill-route-discovery`, pass 3 of 4
Branch: `codex/blackhole-evolve/20260621T063524.176919-add-or-extend-local-validation-for-skill-route-d`
Rollback ref: `refs/rollback/20260621T063207Z-skill-route-discovery-pass3`
Rollback artifact: `artifacts/rollback/20260621T063207Z-skill-route-discovery-pass3-checkpoints.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: public repository exposes a COMPASS Skills package with `skills/`, SKILL.md-style local workflows, task clarification, repo-local memory, handoff prompts, and profile state. This supports bounded config/documentation/test review, not profile or memory writes from repository presence.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public repository exposes domain skills, a director route, packaged scripts, and scaffolds for Three.js game work. This supports local validation checkpoints, not upstream installer, scaffold, browser helper, or asset execution during discovery.
- `https://github.com/baskduf/FableCodex`: public repository exposes Codex workflow gates and verification habits. This supports keeping mixed Codex/skill/workflow evidence in `skill_route_discovery` first before any broader harness evaluation.

## Hypothesis

Pass 3 already selects a local `test` lane for mixed FableCodex/Three.js route
profiles and a queued local `config` lane for COMPASS-style state handoff. An
operator-visible checkpoint list in `pass3_handoff_packet` makes that active and
queued work directly reviewable without requiring supervisors to inspect nested
queue rows.

## Change

- Added `pass3_handoff_packet.operator_checkpoint_list` to
  `src/blackhole_agent/harness_eval.py`.
- Extended `tests/test_harness_eval.py` and
  `tests/fixtures/local_harness_eval/skill_route_discovery_lane_pass3_selection.json`
  to assert selected and queued checkpoints, queue fingerprints, body-free
  evidence handling, and denial flags.
- Documented the pass-3 checkpoint surface in `docs/skill-route-discovery.md`.

Self-model: unchanged. The current self-model already prefers locally validated
behavior changes and bounded external skill-route handling; this pass did not
contradict it.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile"`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery or mixed"`: passed, 15 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or proposal_interpretation"`: passed, 5 tests.

## Review Notes

- The new checkpoint list does not add local lanes.
- It does not install, enable, clone, or execute upstream skills.
- It does not export raw upstream evidence URLs, raw source URLs, target paths,
  or upstream bodies in the harness output.
- Provider launch, remote execution, external harness execution, external agent
  activation, and external skill activation remain denied.
