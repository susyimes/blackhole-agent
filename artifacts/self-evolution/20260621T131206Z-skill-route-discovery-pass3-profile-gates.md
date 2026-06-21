# Skill Route Discovery Pass 3 Profile Gates

- Source digest: `github-growth-20260621T131207.804228Z`
- Capability theme: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260621T131314.419997-add-a-bounded-local-skill-route-discovery-valida`
- Rollback ref: `refs/rollback/20260621T131206Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260621T131206Z-skill-route-discovery-pass3.txt`

## Evidence

- `https://github.com/majidmanzarpour/threejs-game-skills` shows a game/frontend skill bundle with director routing, scaffold, browser/QA, and provider/asset signals.
- `https://github.com/dongshuyan/compass-skills` remains state-handoff and skill-ecosystem evidence.
- `https://github.com/baskduf/FableCodex` remains Codex workflow-gate evidence.

These are local routing lessons only. No upstream code, installer, scaffold, browser helper, provider launch, profile write, memory write, or external skill activation was executed.

## Hypothesis

Pass-3 handoff already queued bounded local lanes, but final profile activation gates should also carry the profile acceptance contract. That gives the supervisor one operator-visible surface proving each route profile has its local validation gate and metadata requirements ready before final-pass replay.

## Changes

- Threaded `profile_lane_acceptance_contract` into `skill_route_discovery_pass3_handoff_packet`.
- Extended `profile_activation_gates` with contract status, validation gate, required metadata, acceptance gates, and contract readiness per profile.
- Kept contract profiles visible even when a blocked profile cannot be queued for replay.
- Added positive fixture assertions for FableCodex, Three.js game/frontend, and COMPASS state-handoff validation gates.
- Added a negative regression where a broken state-handoff privacy boundary blocks pass-3 activation.
- Documented the pass-3 contract handoff in `docs/skill-route-discovery.md`.

## Validation

- `python -m compileall -q src\blackhole_agent\harness_eval.py src\blackhole_agent\skill_routing.py`
- `python -m pytest tests/test_harness_eval.py -q -k "pass3_selects_bounded_lane_per_profile or pass3_blocks_when_profile_contract_is_not_ready"`: 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: 9 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: 2 passed.
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`: 17 passed.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_docs_contracts.py -q`: 155 passed.

## Review Notes

- The self-model was read and left unchanged. It already supports local, rollback-backed, validated behavior changes and did not need a new preference for this pass.
- The pass-3 gate remains metadata-only and bounded to documentation, config, test, and code_patch lanes.
- Raw evidence URLs, raw source URLs, raw target paths, upstream bodies, external skill code, provider runtime launch, remote execution, and external harness execution remain denied in the harness output.
