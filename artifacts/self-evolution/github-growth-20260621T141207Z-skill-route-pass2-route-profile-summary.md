# Skill Route Pass-2 Route Profile Summary

- Source digest: `github-growth-20260621T141207.926892Z`
- Capability theme: `skill-route-discovery`, pass 2 of 4
- Branch: `codex/blackhole-evolve/20260621T141403.073084-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/blackhole-agent/20260621T141206Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260621T141206Z-skill-route-discovery-pass2.md`

## Evidence

- `https://github.com/majidmanzarpour/threejs-game-skills`: public skill bundle for Three.js game work with installable skills, QA checks, provider/key boundaries, and local game scaffolding.
- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem for clarification, repo-local memory/task state, handoff prompts, and local collaboration profile.
- `https://github.com/baskduf/FableCodex`: public Codex workflow/plugin repository with evidence gates, local ledgers, and verification workflow guidance.

## Hypothesis

Pass-2 skill-route handoff is easier to replay if `pass2_handoff_packet`
surfaces a compact per-profile acceptance summary. The supervisor should see
that FableCodex-style Codex/workflow evidence remains `skill_route_discovery`
first, Three.js-style game/frontend evidence remains a bounded local `test`
lane, and COMPASS-style state handoff remains a queued local `config` lane,
without treating any upstream repository as installable or executable.

## Change

- Added `route_profile_acceptance_summary` to `skill_route_discovery_pass2_handoff_packet`.
- The summary repeats accepted profile rows, selected versus queued pass role, expected first local lane, validation gate, required validation commands, and execution-denial flags.
- Extended the pass-2 regression to assert the three carried profiles, allowed lanes, `skill_route_discovery_first`, and raw URL omission.
- Documented the summary in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 21 tests.

## Review Notes

- Self-model left unchanged. Its current preference already matches this run:
  reversible local evolution, narrow safety review, and validation-backed scope.
- External evidence was used only as body-free route-profile context.
- No install, clone, runtime execution, provider launch, remote execution, or raw upstream body export was added.
