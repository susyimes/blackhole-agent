# Skill Route Discovery Pass 2 Acceptance Contract

Source digest: `github-growth-20260621T073207.859828Z`

Branch: `codex/blackhole-evolve/20260621T073339.188620-add-or-extend-local-tests-that-exercise-skill-ro`

Rollback point: `artifacts/rollback/20260621T073207Z-skill-route-pass2-local-lanes.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: public COMPASS Skills repository describes local skill workflows for task clarification, task memory, handoff prompts, and user profile state. This supports a bounded config/state-handoff review lane, not automatic local profile or memory writes.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public game/frontend skill repository describes domain-specific Three.js browser game workflows. This supports local documentation/test validation lanes, not upstream scaffold execution or provider launch.
- `https://github.com/baskduf/FableCodex`: public Codex-style workflow repository supports keeping mixed Codex, skill, and workflow evidence in `skill_route_discovery` before any broader agent harness route.

## Hypothesis

Pass 2 already exposes selected and queued bounded lanes, but the supervisor still has to infer whether each lane satisfied the concrete acceptance gates that make it replayable. A body-free `local_lane_acceptance_contract` inside `pass2_handoff_packet` makes the selected test lane and queued config lane directly reviewable before the next pass while preserving all runtime denials.

## Change

- Added `pass2_handoff_packet.local_lane_acceptance_contract` in `src/blackhole_agent/harness_eval.py`.
- The contract records per-row bounded-lane acceptance gates for local validation, no runtime action, denied external skill/harness/provider/remote execution, and omitted raw upstream evidence.
- It also records the mixed-route gate: FableCodex-style Codex/workflow/skill evidence keeps `skill_route_discovery` primary and keeps the secondary harness lane blocked until local corroboration.
- Added pass-2 regression assertions in `tests/test_harness_eval.py`.
- Documented the contract in `docs/skill-route-discovery.md` and `docs/architecture.md`.

Self-model: unchanged. The existing self-model already supports locally validated evolution with narrow safety boundaries; this run made that preference concrete in controller output rather than changing the description.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff or skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls"`: passed, 2 tests.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed.

## Review Notes

- The contract is metadata-only and body-free.
- It adds no new allowed lanes.
- It does not install external skills, execute upstream code, launch providers, execute a secondary harness, push remotely, or export raw GitHub URLs in harness output.
