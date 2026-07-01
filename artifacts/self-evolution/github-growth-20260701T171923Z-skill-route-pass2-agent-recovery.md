# Skill Route Pass 2 Agent Recovery Contract

Source digest: `github-growth-20260701T171923.099727Z`

Hypothesis:

The active pass-2 skill-route window needs an operator-visible recovery contract for adjacent general-agent evidence.
zhengxi-views can remain the only skill-route candidate, while Qwen-AgentWorld, Fundamental-Ava, looper, and
open-reverselab stay gated behind local `agent_harness_eval_required` before any follow-up lane is selected.

Change:

- Added a current-digest pass-2 mapping for `github-growth-20260701T171923.099727Z`.
- Added `adjacent_agent_recovery_contract` to the current digest pass-2 local validation lane.
- Added a replay fixture and focused regression test for the current digest.
- Documented the recovery surface in `docs/skill-route-discovery.md`.

Boundary:

- No upstream code is installed, cloned, imported, or executed.
- Raw source URLs, replay command bodies, target paths, and upstream bodies remain omitted from route output.
- open-reverselab remains review-only at the offensive-behavior boundary.

Validation:

- `python -m compileall -q src/blackhole_agent`: passed.
- `pytest tests/test_harness_eval.py -q -k "current_digest_20260701T171923 or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed, 2 tests.
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed, 10 tests.
