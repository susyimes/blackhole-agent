# Skill Route Discovery Pass 1 Bounded Lane

- Source digest: `github-growth-20260629T002729.571892Z`
- Capability window: `skill-route-discovery`, pass 1 of 4
- Rollback artifact: `artifacts/rollback-20260629T002728Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260629T002728Z-skill-route-pass1`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

## Hypothesis

The current digest should produce an operator-visible pass-1 lane before any
activation: zhengxi-views and COMPASS evidence can become bounded local
skill-route validation rows, while Qwen-AgentWorld and Looper stay adjacent
agent-harness evaluation rows with no inherited skill-route authority.

## Local Change

- Added a current digest branch to `current_run_pass1_activation_readiness`.
- Added a replay fixture for the 2026-06-29 pass-1 bounded lane.
- Added direct harness and skill-routing regression tests.
- Documented the current digest behavior in `docs/skill-route-discovery.md`.

## Boundaries

- Runtime action remains `none`.
- External skill activation, external agent activation, external harness
  execution, provider launch, remote execution, profile writes, and memory
  writes remain denied.
- Raw source URLs, raw evidence URLs, raw target paths, replay commands, and
  upstream bodies are not exported by the operator panel.

## Validation

Planned local validation:

```powershell
pytest tests/test_skill_routing.py -q -k "current_digest_20260629_pass1_bounded_lane"
pytest tests/test_harness_eval.py -q -k "current_digest_20260629_pass1_bounded_lane"
pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or current_digest_20260629_pass1_bounded_lane"
pytest tests/test_skill_routing.py -q
```

## Review Notes

- External evidence remains repository-level and body-free; this is route
  validation evidence, not upstream implementation parity.
- The self-model was read and left unchanged because its current preference
  already matches the run: prefer rollback-backed, locally validated behavior
  changes while keeping runtime policy external.
