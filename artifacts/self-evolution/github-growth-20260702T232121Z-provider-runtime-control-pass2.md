# Provider Runtime Control Pass 2

Source digest: `github-growth-20260702T232121.733180Z`

## Evidence Review

- `https://github.com/lyra81604/zhengxi-views` exposes a public Agent Skill shape with `SKILL.md`, `skill.yml`, references, evals, scripts, source-cited workflow language, and an advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld` is a broader general-agent benchmark/world-model signal, not a direct skill-route activation signal.
- `https://github.com/TianhangZhuzth/Fundamental-Ava` is a broader autonomous/social agent signal, not a direct local runtime activation signal.
- `https://github.com/ksimback/looper` is a review-gated agent-loop signal, useful for workflow control pressure but still outside direct external harness execution.

## Hypothesis

The provider/runtime slice already has preflight diagnostics, recovery hints, and a promotion checkpoint. The next useful pass should make the supervisor-facing next step explicit: provider replay can be ready while the selected bounded validation lane is still blocked. That distinction prevents diagnostics from being mistaken for provider launch or promotion authority.

## Change

- Added `provider_runtime_activation_packet` to `skill_route_discovery_lane` output.
- The packet joins current-action provider preflight, provider-runtime promotion checkpoint, and validation readiness into one body-free scheduler row.
- The packet distinguishes:
  - provider replay ready plus selected validation ready,
  - provider replay ready but validation lane still blocked,
  - degraded/review provider replay,
  - provider replay repair required.
- Added a current-digest provider-runtime-control pass-2 fixture covering the new packet.
- Updated aggregate harness regression counts and docs.
- Hardened `tests/conftest.py` so pytest always imports this worktree's `src` first when another checkout or editable install exists.

## Self-Model

`docs/self-model.md` was left unchanged. The existing self-model already names provider/runtime preflight checks and rollback-backed local evolution as valid growth areas; no new self-description was needed.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass or current_digest_20260702T232121"` passed.
- `python -m pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q` passed.
- `python -m pytest tests/test_harness_eval.py -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed.

## Rollback

- Rollback ref: `refs/rollback/blackhole-agent/20260702T232121Z-provider-runtime-control-pass2`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260702T232121Z-rollback.md`

## Review Notes

- No provider was launched.
- No external harness was executed.
- No upstream repository code was cloned, installed, or run.
- The activation packet is replay and validation guidance only. It keeps provider launch, remote execution, external harness execution, and supervisor promotion denied.
- The current digest packet reports provider replay ready while validation lane selection remains blocked, which is the expected pass-2 state.
