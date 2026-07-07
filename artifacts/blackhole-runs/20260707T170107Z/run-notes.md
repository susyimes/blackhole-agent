# Skill Route Discovery Pass 4 Completion

- Source digest: `github-growth-20260707T170109.447884Z`
- Branch: `codex/blackhole-evolve/20260707T170205.979547-add-or-extend-local-tests-for-skill-route-discov`
- Rollback ref: `refs/heads/rollback/blackhole-evolve-20260707T170107Z`
- Rollback artifact: `artifacts/blackhole-runs/20260707T170107Z/rollback.md`

## Evidence Reviewed

- `https://github.com/Pluviobyte/rnskill`: SKILL.md-compatible agent skill collection with install and plugin-marketplace pressure.
- `https://github.com/hdz717/reverse-flow-skill`: Codex/AI Agent reverse-flow skill workflow with local sandbox and run/execution pressure.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent reverse-flow skill workflow with local sandbox and run/execution pressure.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate, not a skill package.
- `https://github.com/shepherd-agents/shepherd/pull/33`: Shepherd activity signal for local harness evaluation, not direct runtime adoption.

## Hypothesis

The final pass should expose an operator-visible completion handoff for the current skill-route policy window. Skill/workflow evidence should map only to documentation, config, test, or code_patch lanes, while Shepherd and Agents-A1 activity stays behind `agent_harness_eval_required`. Route hints must remain metadata and never grant permissions or runtime authority.

## Changes

- Added `skill_route_discovery_current_digest_20260707T170109_pass4_completion_handoff`.
- Added a route-hint policy regression subpacket:
  - `skill_route_discovery`: documentation, config, test, code_patch.
  - `agent_harness_eval`: documentation, test, code_patch after local harness evaluation.
  - no runtime action, external activation, provider launch, remote execution, promotion, or restart authority.
- Added the frozen `current_digest_20260707T170109_pass4_completion.json` fixture.
- Added focused skill-route and docs-contract coverage.
- Documented the handoff in architecture and skill-route discovery docs.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. It already says local evolution should be rollback-backed, locally validated, and explicit about uncertainty; this run did not produce evidence that the self-model should be rewritten.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T170109`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T170109 or 20260707T164109 or 20260707T154109"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k "20260707T170109 or 20260707T164109 or 20260707T154109"`: passed, 3 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k "route_hint_policy or skill_route_discovery_enforces_lanes"`: passed, 1 test.

## Review Notes

- No external skill code was installed, cloned, executed, or activated.
- No Shepherd runtime, harness, provider, remote execution, promotion, push, or restart action was performed.
- Ad hoc `python -` imports without pytest can resolve the main checkout package unless `src` is inserted on `sys.path`; pytest validation uses this worktree through `tests/conftest.py`.
