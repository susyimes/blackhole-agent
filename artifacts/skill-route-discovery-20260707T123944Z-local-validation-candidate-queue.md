# Skill Route Discovery Local Validation Candidate Queue

Source digest: github-growth-20260707T123946.895963Z
Run timestamp: 20260707T123944Z
Rollback ref: refs/blackhole-rollback/20260707T123944Z

## Evidence

- https://github.com/lingbol088-spec/reverse-flow-skill: Codex/AI Agent skill repository with `skills/reverse-flow/SKILL.md`, local sandbox wording, and run/install pressure that should remain discovery pressure only.
- https://github.com/Pluviobyte/rnskill: generic AI Agent Skills collection for Codex/Claude-compatible `SKILL.md` workflows, with docs, tools, marketplace metadata, and install pressure that should remain discovery pressure only.

## Hypothesis

Skill-route discovery already classifies reverse-flow and rnskill into bounded local lanes, but the controller map should expose a direct local validation candidate queue carrying route profiles before activation. The queue should preserve `runtime_action: none`, omit raw evidence URLs and replay commands, and limit lanes to documentation, config, test, and code_patch.

## Changes

- Added `local_validation_candidate_queue` to `build_skill_route_discovery_proposal_lane_map`.
- Added queue rows with route profiles, selected item IDs, source URL hashes, selected/queued bounded lanes, validation gates, and denial booleans.
- Added regression coverage for the current reverse-flow/rnskill fixture.
- Documented the generic skill workflow lane and queue boundary.
- Left `docs/self-model.md` unchanged because it already states the rollback-backed local validation preference used by this run.

## Validation

- `pytest tests/test_skill_routing.py -q -k "20260707T121946"`: passed, 2 tests.
- `pytest tests/test_skill_routing.py -q`: passed, 377 tests.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 7 tests.

## Review Notes

- No external skill code was installed, enabled, or executed.
- Raw evidence URLs are used only in the source digest fixture and artifact evidence summary; the new queue surface exports hashes and selected item IDs only.
- Activation remains supervisor/controller recomputation after local validation.
