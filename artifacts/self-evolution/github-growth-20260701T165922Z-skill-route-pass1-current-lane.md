# Skill Route Discovery Pass 1 Current Lane

Source digest: `github-growth-20260701T165922.952638Z`

Hypothesis: the current zhengxi-views trend evidence is useful only if the
controller exposes it as a bounded local skill-route lane while adjacent
general-agent projects remain behind `agent_harness_eval_required` until local
harness validation succeeds.

Change set:
- Added a digest-specific pass-1 route mapping for
  `p1-skill-route-discovery-for-zhengxi-views`.
- Added a replay fixture for the current digest and proposal anchors.
- Added a direct route-map regression test for the current pass-1 lane.
- Updated `docs/skill-route-discovery.md` with the current digest decision.

Rollback:
- `artifacts/rollback/20260701T165921Z-skill-route-discovery-pass1-current-lane.md`

Validation:
- `python -m pytest tests/test_skill_routing.py -q -k 20260701T165922` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "20260701T165922 or local_harness_eval_runs_pass_and_fail_fixtures"` passed.
- `python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.

Review notes:
- Self-model was read and left unchanged; it already supports reversible,
  locally validated behavior changes and did not add a sharper decision rule for
  this pass.
- The new lane does not execute upstream code, install packages, launch
  providers, export raw evidence URLs, or grant runtime action.
- `p4-automation-bug-agent-eval-case` is represented as review-only route
  context at the offensive-behavior boundary.
