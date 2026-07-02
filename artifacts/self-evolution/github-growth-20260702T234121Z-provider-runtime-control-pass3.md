# Provider Runtime Control Pass 3

Source digest: `github-growth-20260702T234121.739101Z`

Hypothesis: pass 3 of the provider-runtime-control slice should expose a
current-digest operator recovery workflow before final completion. The workflow
should distinguish provider replay readiness from bounded validation readiness
without exporting provider inputs, raw commands, source URLs, evidence URLs, or
upstream bodies.

Evidence reviewed:
- `https://github.com/lyra81604/zhengxi-views` exposes a public Agent Skill
  package shape with `SKILL.md`, `skill.yml`, references, evals, scripts, and
  source-cited/advice-boundary language.
- `https://github.com/QwenLM/Qwen-AgentWorld`,
  `https://github.com/TianhangZhuzth/Fundamental-Ava`, and
  `https://github.com/ksimback/looper` are general agent project evidence for
  `agent_harness_eval_required`, not direct skill-route activation.

Changes:
- Added `provider_runtime_control_pass3_operator_recovery_workflow` to the
  skill-route harness output.
- Added a frozen current-digest pass-3 local harness fixture.
- Added a focused regression for the pass-3 workflow and updated aggregate
  fixture counts.
- Documented the pass-3 handoff in `docs/skill-route-discovery.md`.

Validation:
- `python -m pytest tests/test_harness_eval.py -q -k "20260702T234121_provider_runtime_control_pass3"` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass or 20260702T234121_provider_runtime_control_pass3"` passed.

Self-model: read and left unchanged. It remains descriptive context rather than
an executable route source, and this run had a direct behavior improvement with
local validation coverage.

Rollback:
- Rollback ref: `refs/rollback/blackhole-agent/20260702T234121Z-provider-runtime-control-pass3`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260702T234121Z-rollback.md`

Review notes:
- The new workflow is replay-only. It exports command hashes, selected item IDs,
  source hashes, lane names, counts, and denial booleans.
- Provider launch, external harness execution, remote execution, supervisor
  promotion, and external skill or agent activation remain denied.
