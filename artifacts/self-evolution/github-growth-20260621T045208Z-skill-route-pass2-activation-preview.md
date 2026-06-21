# Skill Route Discovery Pass 2 Activation Preview

Source digest: `github-growth-20260621T045208.520071Z`
Capability window: `skill-route-discovery`, pass 2 of 4
Branch: `codex/blackhole-evolve/20260621T045308.039970-add-or-update-a-local-validation-test-lane-for-d`
Rollback artifact: `artifacts/rollback/20260621T045207Z-skill-route-discovery-pass2.md`
Rollback ref: `refs/rollback/20260621T045207Z-skill-route-discovery-pass2`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: public repository exposes a COMPASS Skills package with `skills/`, `skills.sh.json`, and SKILL.md-style local workflows for clarification, task memory, handoff, and user profile state. This supports bounded state/profile route handling, not profile or memory writes from repository presence.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public repository describes domain-specific agent skills for Three.js browser games, QA, and optional asset workflows. This supports bounded domain validation lanes, not upstream scaffold or asset execution.
- `https://github.com/baskduf/FableCodex`: public repository describes a Codex-style coding-agent workflow. This supports the existing mixed skill/workflow first-route decision through `skill_route_discovery`.

## Hypothesis

Pass 2 already reports selected and queued local lanes, but the operator has to
cross-reference nested queue and manifest surfaces to see what can be replayed
before the next pass. A body-free `bounded_activation_preview` inside
`pass2_handoff_packet` makes the selected current-pass lane and queued bounded
lane directly visible while preserving all existing denials.

## Changes

- Added `pass2_handoff_packet.bounded_activation_preview` in `src/blackhole_agent/harness_eval.py`.
- The preview reports selected and queued lane counts, selected-item citation mode, route profiles, replay commands, provider-runtime replay commands, per-row activation-preview steps, and blocker codes.
- It repeats denials for runtime action, external skill activation, external agent activation, external harness execution, provider launch, remote execution, raw evidence URL export, raw source URL export, raw target path export, and upstream body export.
- Updated `tests/test_harness_eval.py` to assert the pass-2 preview for the current COMPASS/FableCodex/Three.js fixture.
- Updated `docs/skill-route-discovery.md` and the docs contract test.

## Self-Model

`docs/self-model.md` was read and left unchanged. It is consistent with this
run's behavior: prefer locally validated behavior changes over report-only
work, keep rollback and validation explicit, and block only offensive,
abusive, unauthorized, or privacy-leaking paths.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "pass2_handoff_packet or skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls"` passed: 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed: 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or mixed_local_lane_probe or validation_readiness_summary"` passed: 11 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery or mixed"` passed: 15 tests.

## Review Notes

The preview is derived from already-local pass-2 queue rows and does not inspect
or import upstream bodies. It is an operator replay surface, not a new
activation authority. Evidence remains repository-level, so claims stay limited
to local documentation, config, test, and code_patch lanes.
