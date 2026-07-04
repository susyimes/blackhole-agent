# Skill Route Discovery Pass 1 Current Window

- Source digest: `github-growth-20260704T162434.547303Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/20260704T162535Z-skill-route-discovery-pass1-current-window`
- Rollback artifact: `artifacts/rollback/20260704T162535Z-skill-route-discovery-pass1-current-window/rollback-point.md`

## Evidence

Reviewed the bounded evidence URL for
`lingbol088-spec/reverse-flow-skill`. The public repository describes an AI
Agent/Codex reverse-flow skill with a `skills/reverse-flow` package, local
sandbox/CTF defaults, workflow steps, and install/script examples. This is
classification evidence only: upstream setup and runtime pressure remain
diagnostics.

## Hypothesis

The current digest should produce an operator-visible pass-1 lane that routes
Codex skill workflow evidence through `skill_route_discovery_first`, keeps
generic skill workflow evidence inside bounded local lanes, and sends general
agent projects without skill route hints to `agent_harness_eval_required`.

## Local Change

- Added source digest recognition for `github-growth-20260704T162434.547303Z`.
- Added the focused fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260704T162434_pass1_validation_lane.json`.
- Added regression coverage for the current proposal IDs and lane boundaries.
- Documented the current handling path in `docs/skill-route-discovery.md`.

## Validation

`python -m pytest tests/test_skill_routing.py -q -k 20260704T162434`

Result: passed.

`python -m pytest tests/test_skill_routing.py -q`

Result: passed, 274 tests.

## Review Notes

- Self-model left unchanged; its current preference already supports this
  rollback-backed, locally validated behavior improvement.
- No external skill activation, external harness execution, provider launch,
  remote execution, profile write, memory write, push, promotion, or restart
  was performed.
