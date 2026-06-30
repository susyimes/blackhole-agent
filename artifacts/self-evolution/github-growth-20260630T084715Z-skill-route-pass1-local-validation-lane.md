# Skill Route Pass 1 Local Validation Lane

- Source digest: `github-growth-20260630T084715.195137Z`
- Theme: `skill-route-discovery`
- Capability pass: 1 of 4
- Rollback artifact: `artifacts/self-evolution/github-growth-20260630T084715Z-rollback.md`

## Hypothesis

The current evidence window should become an operator-visible pass-1 local
validation lane rather than a runtime or scheduler change. The zhengxi-views
signal is skill-shaped and can safely map to a bounded local test lane.
Qwen-AgentWorld, looper, and AgentChat are general-agent signals and must stay
behind `agent_harness_eval_required` before documentation, test, code_patch,
runtime, scheduler, or loop-control behavior is selected.

## Evidence Scope

Reviewed only the carried proposal evidence URLs at repository level and local
digest fixtures. The upstream evidence was treated as body-free route evidence:
repository shape, route hints, item IDs, and public source lineage only.

## Local Change

- Added digest-specific pass-1 routing for
  `github-growth-20260630T084715.195137Z`.
- Added a replay fixture for the current digest.
- Added focused assertions for the zhengxi skill-route lane, adjacent
  general-agent rows, and review-only open-reverselab anchor.
- Updated route-discovery documentation.

## Validation

- `pytest tests/test_harness_eval.py -q -k "20260630T084715 or local_harness_eval_runs_pass_and_fail_fixtures"`
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_harness_eval.py -q`

All validation passed.

## Review Notes

No external skill, agent, harness, provider, runtime, scheduler, remote
execution, profile, memory, raw URL export, replay command export, target path
export, or upstream body authority was added. The self-model was read and left
unchanged because it already describes this run's preference for rollback-backed
local behavior with a narrow safety boundary.
