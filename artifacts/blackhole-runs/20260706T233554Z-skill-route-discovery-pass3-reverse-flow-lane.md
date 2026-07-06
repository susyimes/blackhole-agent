# Skill Route Discovery Pass 3: Reverse-Flow Lane Probe

Source digest: `github-growth-20260706T233555.493310Z`
Branch: `codex/blackhole-evolve/20260706T233642.758739-run-a-bounded-local-skill-route-discovery-lane-f`
Rollback point: `artifacts/rollback/20260706T233554Z-skill-route-discovery-pass3-reverse-flow-lane/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`

The public repository presents a Codex / AI Agent skill package shape:
`skills/reverse-flow/SKILL.md`, references, scripts, local sandbox and CTF
framing, install examples, and run examples. Those signals are sufficient for a
bounded local skill-route discovery lane and insufficient for upstream skill
activation or script execution.

## Hypothesis

The existing repository lane probe should be operator-visible enough to decide
whether reverse-flow-style evidence maps to documentation, config, tests, or
code_patch before activation. General workflow or developer-skill repositories
without skill-package markers should remain outside skill-route discovery and
require agent harness evaluation.

## Local Change

- Added a route boundary checklist, accepted outputs, stripped-pressure count,
  activation prerequisite, and operator next action to
  `skill_route_discovery_repository_lane_probe`.
- Marked skill candidates as `skill_route_discovery_first: true` and ignored
  rows as `agent_harness_eval_required`.
- Updated focused tests and documentation for this digest.

## Safety Boundary

- No upstream code was imported or executed.
- Install, run, execute, provider-runtime, runtime-execution, external-harness,
  and remote-execution pressure remains diagnostic only.
- External skill activation, external harness execution, provider launch,
  remote execution, and runtime action remain denied.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k repository_lane_probe`
  passed.
- `python -m pytest tests/test_skill_routing.py -q` passed with 353 tests.
