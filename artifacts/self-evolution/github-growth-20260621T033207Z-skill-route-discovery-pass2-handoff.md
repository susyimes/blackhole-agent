# Skill Route Discovery Pass 2 Handoff

Branch: `codex/blackhole-evolve/20260621T033306.173721-add-or-extend-a-local-skill-route-discovery-vali`

Source digest: `github-growth-20260621T033207.842733Z`

Rollback ref: `refs/rollback/20260621T033207Z-skill-route-discovery-pass2`

Rollback artifact: `artifacts/rollback/20260621T033207Z-skill-route-discovery-pass2.md`

## Evidence

- `https://github.com/dongshuyan/compass-skills`: public repository presents a local skill ecosystem with task clarification, task memory, handoff, and profile state. This supports bounded state/profile route handling, not memory or profile writes from repository presence.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public repository presents specialized Three.js/browser game skills and validation helpers. This supports domain-specific local validation lanes, not upstream scaffold, browser checker, asset generation, or provider execution.
- `https://github.com/baskduf/FableCodex`: public repository presents a Codex-style workflow. In the current digest window, this is treated as mixed Codex/agent/skill/workflow evidence that should prefer `skill_route_discovery` before any broader harness interpretation.

## Hypothesis

Pass 2 of the skill-route-discovery window should expose the selected bounded
local lane, queued bounded lanes, and mixed skill/workflow route decision in one
operator-visible packet. This is more useful than another standalone fixture
because it lets the supervisor continue the slice without inferring from raw
URLs, README-level evidence, or nested route panels.

## Change

- Added `pass2_handoff_packet` to `skill_route_discovery_lane` output.
- The packet reports selected and queued bounded local lanes, selected item IDs,
  candidate source hashes, replay commands, and mixed-route probe status.
- The packet keeps mixed FableCodex-style evidence on
  `skill_route_discovery` first and keeps
  `agent_harness_eval_after_local_corroboration` blocked.
- Updated the pass-2 fixture to the current proposal IDs and mixed
  Codex/agent/skill/workflow FableCodex signal.
- Documented the packet and extended docs contract coverage.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2_fixture or mixed_local_lane_probe or validation_readiness_summary"`: passed, 3 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 9 passed.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures`: passed, 1 passed.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery or mixed"`: passed, 15 passed.

## Review Notes

- Self-model was read and left unchanged. It already describes the preference
  for rollback-backed local behavior over validation-report-only changes, and
  this run followed that preference.
- No upstream skill code, installer, scaffold, browser checker, asset generator,
  provider runtime, remote execution, profile write, memory write, or external
  harness execution was activated.
- The packet remains body-free: source and evidence URLs are represented by
  hashes or selected item IDs in the operator surface.
