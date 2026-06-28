# Skill Route Discovery Pass 3 Proposal Lane Contract

Source digest: `github-growth-20260628T114729.691889Z`
Capability theme: `skill-route-discovery`, pass 3 of 4
Branch: `codex/blackhole-evolve/20260628T114821.472311-create-or-extend-a-local-skill-route-discovery-v`
Rollback artifact: `artifacts/rollback/20260628T194902Z-skill-route-discovery-pass3.md`
Rollback ref: `refs/rollback/20260628T194902Z-skill-route-discovery-pass3`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public SKILL-style repository with source-cited domain workflow, `SKILL.md`, validation/evals, and advisory boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js/browser-game skill workflow evidence with frontend/game validation pressure.
- `https://github.com/dongshuyan/compass-skills`: public COMPASS skill ecosystem evidence for state/profile handoff, local memory, and clarification workflow.

## Hypothesis

The existing pass-3 route-profile handoff was ready and bounded, but operators still had to infer how the active proposal IDs from this wake mapped onto accepted route-profile lanes. A nested proposal-level contract should make the current pass replayable before activation without granting upstream skill execution, provider launch, or raw evidence export.

## Change

- Added `proposal_lane_activation_contract` under `pass3_handoff_packet`.
- The contract maps active skill-route proposal IDs to accepted route profiles and bounded local lanes:
  - `p1-skill-route-discovery-generic` -> `generic_skill_workflow` -> `documentation`
  - `p2-game-frontend-skill-profile` -> `game_frontend_workflow` -> `test`
  - `p3-skill-ecosystem-state-handoff` -> `skill_ecosystem_state_handoff` -> `config`
- Adjacent agent-harness proposals remain in `blocked_adjacent_proposal_ids`.
- Raw source URLs, evidence URLs, target paths, upstream bodies, runtime action, external skill/agent activation, external harness execution, provider launch, and remote execution remain denied.
- Updated the current pass-3 local harness fixture and documentation.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane` -> passed, 10 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` -> passed, 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs` -> passed, 1 passed.
- Manual patched-output probe with `PYTHONPATH=src` confirmed `proposal_lane_activation_contract.status == ready` and no raw GitHub URL in the serialized contract.

## Review Notes

- Self-model left unchanged: the current file already supports rollback-backed local evolution and does not conflict with this bounded local validation change.
- No upstream code was cloned, installed, imported, or executed.
- A plain `python` probe without `PYTHONPATH=src` initially loaded an installed package and did not reflect this checkout; the corrected probe used the local source tree.
