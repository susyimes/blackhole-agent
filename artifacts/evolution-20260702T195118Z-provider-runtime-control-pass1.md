# Evolution Run: provider-runtime-control pass 1

- Source digest: `github-growth-20260702T195118.384129Z`
- Branch: `codex/blackhole-evolve/20260702T195208.484949-run-a-bounded-skill-route-discovery-validation-a`
- Rollback point: `artifacts/rollback-20260702T195118Z-provider-runtime-control-pass1.md`
- Theme: `provider-runtime-control`
- Pass: 1 of 4

## Evidence

- `https://github.com/lyra81604/zhengxi-views` stays in `skill_route_discovery` because the carried digest describes agent/skill workflow signals and source-cited validation metadata.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper` stay behind `agent_harness_eval_required` because the carried digest describes general agent projects without local skill workflow evidence.

## Hypothesis

The active provider-runtime-control slice benefits from a replayable current-digest fixture that proves a harmless local provider preflight sample can make the provider-runtime sample gate ready without granting provider launch, remote execution, or full capability-slice completion during pass 1.

## Change

- Added `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260702T195118_provider_runtime_control_pass1.json`.
- Added focused regression coverage in `tests/test_harness_eval.py`.
- Updated `docs/skill-route-discovery.md` and its docs contract to clarify that pass-1 provider-runtime sample readiness is not supervisor completion.
- Left `docs/self-model.md` unchanged because it already matches this run's preference for local, rollback-backed validation and does not act as a permission source.

## Validation

- `pytest tests/test_harness_eval.py::test_skill_route_discovery_current_digest_20260702T195118_provider_runtime_control_pass1 -q` passed.
- `pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q` passed.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_bounded_matrix` passed.

## Review Notes

- The full `tests/test_harness_eval.py -q -k 20260702T195118` command initially timed out while rendering an overbroad serialization assertion over a large output. The assertion was narrowed to raw URL/provider-label omission and launch denial; the exact pytest node then passed.
- No provider was launched, no external harness was executed, and no upstream repository code was cloned or run.
