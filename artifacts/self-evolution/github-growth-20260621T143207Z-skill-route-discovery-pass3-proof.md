# Skill Route Discovery Pass 3 Proof

Source digest: `github-growth-20260621T143207.777252Z`
Capability window: `skill-route-discovery`, pass 3 of 4
Branch: `codex/blackhole-evolve/20260621T143319.040562-add-a-local-skill-route-discovery-validation-lan`
Rollback artifact: `artifacts/rollback/20260621T143207Z-skill-route-discovery-pass3.md`
Rollback ref: `refs/rollback/blackhole-agent/20260621T143207Z-skill-route-discovery-pass3`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: COMPASS presents a multi-skill local ecosystem for clarification, repo-local task memory, handoff prompts, and collaboration profile state.
- `https://github.com/baskduf/FableCodex`: FableCodex is treated as a Codex workflow gate signal, not an installable upstream workflow.
- `https://github.com/majidmanzarpour/threejs-game-skills`: Three.js Game Skills is treated as a domain/game frontend skill bundle with local validation and asset/provider boundaries.

## Hypothesis

The existing pass-3 handoff names the selected and queued bounded lanes, but the
active proposals need an operator-visible proof that each route profile has
enough local validation evidence before final activation. A body-free
`profile_validation_proof` packet can bind each profile to a bounded local lane,
selected item IDs, hashed candidate sources, local artifact proof, replay
commands, and the profile acceptance contract without importing upstream skill
code or expanding runtime permissions.

## Change

- Added `profile_validation_proof` to `skill_route_discovery_pass3_handoff_packet`.
- The proof blocks a profile when its bounded lane, selected item IDs, candidate
  source hashes, matching local artifact proof, required validation commands, or
  acceptance contract are missing.
- Updated focused pass-3 tests for ready and blocked profile-contract cases.
- Documented the pass-3 proof packet in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile or skill_route_discovery_pass3_blocks_when_profile_contract_is_not_ready"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 21 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures or skill_route_discovery_pass3"`: passed, 3 tests.

## Review Notes

- The proof is metadata-only and body-free.
- It exports selected item IDs and candidate source hashes, not raw evidence URLs,
  raw source URLs, raw target paths, or upstream bodies.
- It does not install, enable, run, execute, clone, scaffold, launch providers,
  write profile or memory state, perform remote execution, or activate upstream
  skill code.
- `docs/self-model.md` was read and left unchanged because this run had a direct
  behavior improvement and the current self-model already matches the runtime
  policy boundary.
