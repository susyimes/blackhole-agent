# Skill Route Discovery Pass 2 Run Artifact

Source digest: `github-growth-20260701T094533.713043Z`
Branch: `codex/blackhole-evolve/20260701T094637.690428-add-a-local-validation-lane-for-skill-route-disc`
Rollback ref: `refs/blackhole-rollback/20260701T094532Z-skill-route-discovery`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public `SKILL.md`-style source-cited domain research skill; usable as skill-route evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent project; usable as local harness-eval evidence only.
- `https://github.com/ksimback/looper`: public review-gated agent loop project; usable as local harness-eval evidence only.

## Hypothesis

Repeated upstream `PushEvent` or trend movement should improve the order in
which already-relevant general agent projects are locally evaluated, without
creating runtime authority, external harness execution, provider launch,
upstream skill activation, raw source URL export, or direct code-patch approval.

## Local Changes

- Added bounded general-agent upstream movement priority metadata to
  `build_general_agent_project_eval_lane`.
- Propagated the same priority metadata into `route_activation_preflight`.
- Added a regression fixture using the current pass evidence shape:
  zhengxi-views remains `skill_route_discovery`; Qwen-AgentWorld and looper
  remain `agent_harness_eval_required`.
- Documented that repeated push movement is ordering evidence only.

## Validation

- `pytest tests/test_github_growth.py -q -k "general_agent_project_eval_lane or repeated_upstream_push_activity or skill_route_discovery_boosts_repeated_trend_fork_and_push_activity or route_activation_preflight_keeps_current_skill_window_bounded"`: passed.
- `pytest tests/test_github_growth.py -q`: passed, 97 tests.
- `pytest tests/test_proposal_eval.py -q`: passed, 25 tests.

## Material Actions

- Created rollback ref and rollback artifact before source edits.
- Browsed only the proposal evidence URLs listed above.
- Did not push, promote, restart, launch providers, execute external harnesses,
  activate upstream skill code, or write outside this repository.

## Review Notes

- Priority is intentionally capped and affects local evaluation ordering only.
- Push activity is not treated as standalone implementation evidence.
- Self-model was read and left unchanged because it already describes the
  rollback-backed, locally validated evolution stance used in this run.
