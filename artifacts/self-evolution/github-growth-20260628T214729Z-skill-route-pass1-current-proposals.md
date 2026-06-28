# Skill Route Discovery Pass 1 Current Proposals

- Source digest: `github-growth-20260628T214729.561848Z`
- Branch: `codex/blackhole-evolve/20260628T214815.097069-add-or-extend-local-tests-for-generic-skill-rout`
- Rollback artifact: `artifacts/rollback/20260629T214728Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260629T214728Z-skill-route-discovery-pass1`
- Capability window: `skill-route-discovery`, pass 1 of 4

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: treated as carried digest evidence for a generic public skill workflow. The local lesson is only route classification: skill-term evidence enters `skill_route_discovery` and selects a bounded test lane.
- `https://github.com/majidmanzarpour/threejs-game-skills`: treated as carried digest evidence for a game/frontend skill workflow. The local lesson is that game/frontend profiles stay in documentation, config, test, or code_patch lanes until local frontend validation exists.
- `https://github.com/dongshuyan/compass-skills`: treated as carried digest evidence for skill ecosystem state handoff. The local lesson is metadata-only routing with profile and memory writes denied.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent evaluation evidence. It is intentionally ignored by `skill_route_discovery` unless a selected item carries skill workflow route evidence.

## Hypothesis

The existing pass-1 operator surface is more useful if the exact current proposal IDs can be replayed as a local harness fixture. That lets the supervisor verify the active window before activation without exporting raw evidence URLs, running upstream code, installing skills, or treating adjacent agent projects as skill routes.

## Change

- Added a current-digest pass-1 fixture for `github-growth-20260628T214729.561848Z`.
- Added regression coverage that verifies the three active skill proposals map to `generic_skill_workflow`, `game_frontend_workflow`, and `skill_ecosystem_state_handoff` with only documentation, config, test, or code_patch lanes.
- Verified `Qwen-AgentWorld` remains an ignored adjacent item for this skill-route lane.
- Left `docs/self-model.md` unchanged. The current self-model already says local evolution should be rollback-backed, validated, and uncertainty-explicit; this run did not add evidence that the file is shaping behavior beyond that reminder.

## Review Notes

- No upstream repository code was cloned, installed, or executed.
- No provider runtime, profile write, memory write, external harness execution, or remote execution path was enabled.
- The evidence remains repository-level and body-free; local validation is still required before any activation.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "current_digest_214729_pass1_current_proposals or local_harness_eval_runs_pass_and_fail_fixtures"`: passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 10 tests.
- `python -m pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q -k skill_route_discovery`: passed, 85 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.
