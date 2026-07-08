# Skill Route Discovery Pass 3 Bounded Local Route Eval

Source digest: `github-growth-20260708T223850.754420Z`
Theme: `skill-route-discovery`
Pass: 3 of 4

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: staged Codex/agent skill workflow, local sandbox framing, activation phrase, diagnostic scripts, and a user-choice boundary.
- `https://github.com/Pluviobyte/rnskill`: generic SKILL.md-compatible skill collection with `skills/`, docs, tools, marketplace metadata, and manual install paths.
- `https://github.com/shepherd-agents/shepherd`: adjacent general-agent runtime evidence around reversible traces, replay, and retained outputs; not treated as a skill package.

## Hypothesis

The current pass needs an operator-visible gate that turns skill and route evidence into bounded local lanes before activation:

- reverse-flow-style staged workflow evidence should route to a local `test` lane;
- rnskill-style generic collection evidence should route to a local `documentation` checklist lane;
- Shepherd-style runtime evidence should remain `agent_harness_eval_required` until a local harness eval is replayed.

## Local Change

Added `skill_route_discovery_current_digest_20260708T223850_pass3_local_route_eval_gate` to the proposal lane map. The gate exports body-free proposal rows, keeps raw URLs and replay commands out of output, and records rollback/run artifacts for supervisor replay.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference already matches this run: reversible local implementation is preferred over validation-only reporting, while external activation, unauthorized behavior, and privacy leakage remain outside the allowed lane.

## Validation Plan

- `pytest tests/test_harness_eval.py -q -k 20260708T223850`
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "20260708T223850 or local_harness_eval_runs_pass_and_fail"`

## Validation Results

- `pytest tests/test_harness_eval.py -q -k 20260708T223850`: passed, 1 test.
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "20260708T223850 or local_harness_eval_runs_pass_and_fail"`: passed, 2 tests.
- `pytest tests/test_skill_routing.py -q`: passed, 440 tests.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260708T183850 or skill_route_discovery_current_digest_20260708T195850 or skill_route_discovery_current_digest_20260708T223850"`: passed, 3 tests.

## Review Notes

- No upstream skill was cloned, installed, enabled, or executed.
- Shepherd evidence is preserved as adjacent agent-harness eval pressure only.
- Rollback point: `artifacts/rollback/20260709T000000Z-skill-route-discovery-pass3-bounded-local-route-eval/rollback-point.md`.
