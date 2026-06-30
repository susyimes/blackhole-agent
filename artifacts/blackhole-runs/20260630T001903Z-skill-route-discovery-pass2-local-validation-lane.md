# Skill Route Discovery Pass 2 Local Validation Lane

- Source digest: github-growth-20260630T001904.371161Z
- Capability window: skill-route-discovery, pass 2 of 4
- Rollback: artifacts/rollback/20260630T001903Z-skill-route-discovery-pass2-local-validation.md
- Rollback ref: refs/rollback/blackhole-evolve-20260630T001903Z

## Evidence Review

The carried evidence URL `https://github.com/lyra81604/zhengxi-views` presents
repository-level Skill package shape, including Skill metadata, references,
scripts, eval material, and source-citation/advice boundary pressure. That is
strong enough for a local route validation lane and not strong enough to import,
install, execute, or activate upstream code.

Qwen-AgentWorld and looper remain adjacent general-agent evidence. They should
stay behind the local agent-harness eval lane before any runtime, scheduler, or
controller change is proposed.

## Hypothesis

A current-digest fixture for pass 2 makes the operator-visible validation lane
replayable with the active proposal names. It should classify zhengxi-views as
bounded skill-route evidence, keep COMPASS in the local state-handoff test
lane, and keep Qwen-AgentWorld plus looper as adjacent harness-eval rows.

## Local Change

- Added a current-digest skill-route-discovery fixture for
  `github-growth-20260630T001904.371161Z`.
- Added focused assertions for the current `current_digest_pass2_local_validation_lane`.
- Updated the route-discovery docs with the current pass-2 interpretation.

## Validation

Local gates run:

```powershell
pytest tests/test_harness_eval.py -q -k 20260630T001904
pytest tests/test_harness_eval.py -q -k skill_route_discovery
pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs
pytest tests/test_skill_routing.py -q
```

Results:
- `1 passed, 185 deselected`
- `74 passed, 112 deselected`
- `1 passed, 185 deselected`
- `118 passed`

The lane remains body-free. It does not export raw source URLs, raw evidence
URLs, replay command bodies, target paths, or upstream bodies, and it grants no
install, provider-runtime, external harness, profile write, memory write, or
remote execution authority.
