# Skill Route Pass 2 Adoption Manifest

Source digest: `github-growth-20260622T170624.356588Z`
Branch: `codex/blackhole-evolve/20260622T170728.027713-add-or-extend-a-local-skill-route-discovery-vali`
Rollback ref: `refs/blackhole-rollback/20260622T170623Z-skill-route-pass2`

## Evidence Reviewed

- `https://github.com/baskduf/FableCodex`: Codex workflow gates, plugin-style activation, tests, evals, and verification routines.
- `https://github.com/dongshuyan/compass-skills`: local skill ecosystem, task memory, profile, and handoff workflows with explicit local-data safety boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills`: Three.js/game skills with install commands, sibling skills, asset/provider workflow pressure, and QA expectations.
- `https://github.com/lyra81604/zhengxi-views`: source-cited domain skill with public corpus, scripts, fund data, and explicit non-advice boundary.

## Hypothesis

Skill-like repositories should be visible to the controller as bounded local validation lanes before any adoption decision. A single operator-facing manifest reduces ambiguity by showing the selected local lane, replay command, blocked external actions, and proof state without adding runtime authority.

## Change

- Added `adoption_manifest` to `build_skill_route_discovery_proposal_lane_map`.
- The manifest is body-free and reports candidate source hashes rather than raw source URLs.
- It marks adoption ready only when candidates remain inside documentation, config, test, or code_patch lanes, local validation is required, runtime action is none, and required first-route proof is present.
- It blocks install, execute, upstream skill activation, provider launch, external harness execution, remote execution, raw source URL export, and upstream body export.
- Updated the skill-route documentation and regression test for the carried FableCodex, COMPASS, and Three.js profiles.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference for rollback-backed, locally validated evolution matches this run; no evidence showed it needed to become more specific.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery_proposal_lane_map_bounds_recognized_skill_evidence`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 25 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 30 tests.
- `git diff --check`: passed with Windows line-ending warnings only.

## Review Notes

- No external repository code was cloned, installed, executed, or imported.
- The new manifest is derived from existing lane-map inputs; it does not create new proposal lanes.
- Activation, promotion, push, and restart remain supervisor responsibilities.
