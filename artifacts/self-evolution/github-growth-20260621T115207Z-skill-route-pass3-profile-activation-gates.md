# Skill Route Discovery Pass 3 Profile Activation Gates

Source digest: `github-growth-20260621T115207.818603Z`

Rollback point:

- Branch: `codex/blackhole-evolve/20260621T115505.505193-add-or-extend-local-skill-route-discovery-valida`
- Rollback ref: `refs/rollback/20260621T115206Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260621T115206Z-skill-route-discovery-pass3.md`

Evidence reviewed:

- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem with task clarification, repo-local task memory, handoff prompts, and local profile workflows.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js/browser game skill bundle with game/frontend validation signals.
- `https://github.com/baskduf/FableCodex`: public Codex-style workflow/skill evidence with verification and routing habits.

Hypothesis:

Pass-3 handoff is more useful to the supervisor if it exposes a body-free per-profile activation gate before final pass replay. COMPASS-style state handoff should remain config-lane only, Three.js game skill workflows should remain test-lane only, and FableCodex-style mixed Codex/workflow evidence should preserve `skill_route_discovery_first`.

Changed files:

- `src/blackhole_agent/harness_eval.py`
- `tests/test_harness_eval.py`
- `docs/skill-route-discovery.md`

Implementation:

- Added `profile_activation_gates` to `skill_route_discovery_pass3_handoff_packet`.
- Added `skill_route_discovery_pass3_profile_activation_gates()` to aggregate queued pass-3 rows by route profile.
- The gate records selected bounded local lanes, queue roles, selected item IDs, hashed candidate sources, replay commands, activation blockers, and denial flags without exporting raw source URLs or upstream bodies.
- The gate grants no runtime action, no provider launch, no external harness execution, no upstream skill activation, no profile or memory write, and no remote execution.
- Updated the pass-3 regression to assert the COMPASS, Three.js, and FableCodex route-profile outcomes.
- Documented the new pass-3 gate in `docs/skill-route-discovery.md`.

Self-model:

- Left `docs/self-model.md` unchanged. Its current preference already matches this run: local evolution is allowed when rollback-backed, locally validated, and explicit about uncertainty.

Validation:

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile"`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 21 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

Review notes:

- External evidence was used only as body-free route-profile context.
- The change adds an operator-visible behavior path and tests; it does not add allowed lanes.
- Activation and restart remain supervisor responsibilities.
