# Skill Route Discovery Pass 1 Current Window

Source digest: `github-growth-20260629T061942.961537Z`
Branch: `codex/blackhole-evolve/20260629T062041.449258-add-or-update-a-local-skill-route-discovery-vali`
Rollback artifact: `artifacts/rollback/20260629T061940Z-skill-route-discovery-pass1-current-window.md`
Rollback ref: `refs/rollback/20260629T061940Z-skill-route-discovery-pass1-current-window`

## Evidence

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/QwenLM/Qwen-AgentWorld/issues/2`

## Hypothesis

The active pass-1 skill-route window should expose one replayable local lane
that maps skill ecosystem and generic skill workflow evidence into bounded
documentation/config/test/code_patch lanes, while keeping general-agent project
and issue activity behind `agent_harness_eval_required` before implementation.

## Local Change

- Added a current source-digest branch to
  `skill_route_discovery_current_run_pass1_activation_readiness`.
- Added a replay fixture for the 20260629T061942 source digest.
- Added focused assertions that COMPASS selects the test lane, zhengxi-views
  selects the documentation lane, and Qwen-AgentWorld repository plus issue
  activity remain adjacent agent-harness evaluation evidence.
- Documented the current digest interpretation in `docs/skill-route-discovery.md`.

## Validation

- `python -m compileall src/blackhole_agent/skill_routing.py`
- `pytest tests/test_harness_eval.py -q -k "current_digest_20260629T061942_pass1_current_window or test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_current_digest`
- `pytest tests/test_skill_routing.py -q -k "current_digest or pass1"`

## Review Notes

- No upstream code was installed, cloned, executed, or activated.
- Raw evidence URLs, replay command bodies, target paths, and upstream bodies
  remain omitted from the operator panel.
- The self-model was read and left unchanged because its current preference
  already matches this run: prefer rollback-backed, locally validated behavior
  improvements over standalone validation reports.
