# Skill Route Discovery Pass 1 Profile Contracts

Source digest: `github-growth-20260621T123207.823445Z`

Branch: `codex/blackhole-evolve/20260621T123314.312311-add-a-local-validation-lane-for-game-frontend-sk`

Rollback point: `artifacts/rollback/20260621T123207Z-skill-route-discovery-pass1.txt`

## Evidence

- `https://github.com/majidmanzarpour/threejs-game-skills`: public Three.js game skill bundle with director routing, browser game workflow, QA checks, screenshots/canvas validation, scaffold boundaries, and provider/asset safeguards.
- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem/state handoff signal with task clarification, local memory/profile concepts, handoff prompts, and privacy/state boundary pressure.
- `https://github.com/baskduf/FableCodex`: public Codex skill/workflow signal with workflow gates, plugin routing, examples, tests/evals, ledgers, and verification habits.

## Hypothesis

Pass-1 skill-route windows already keep candidate lanes bounded, but operators
still have to correlate the pass-1 anchoring proposal rows with the separate
profile acceptance panel. Carrying a trimmed profile contract on each pass-1
skill-route row improves local replay and review without granting any new
lanes or activation authority.

## Change

- `pass1_validation_queue` now embeds `profile_contracts` on each skill-route
  anchoring proposal row.
- The queue reports `profile_contract_status`, `profile_contract_count`, and
  `ready_profile_contract_count`.
- The current pass-1 test asserts the COMPASS state-handoff gate, Three.js game
  frontend gate, and FableCodex first-route proof are visible directly on the
  proposal rows.
- `docs/skill-route-discovery.md` documents the pass-1 row-level profile
  contract as replay metadata only.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "current_window_pass1 or skill_route_discovery_lane"`: passed, 10 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py tests/test_skill_routing.py tests/test_proposal_eval.py tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 59 tests.

## Review Notes

- Self-model was read and left unchanged. It already matches the current run's
  preference for rollback-backed, locally validated behavior changes and did
  not need to become a permission source.
- The change is body-free and does not export raw upstream URLs in harness
  output beyond existing hashed surfaces.
- Runtime action, external skill activation, external harness execution,
  provider launch, remote execution, raw source URL export, raw target path
  export, and upstream body export remain denied.
