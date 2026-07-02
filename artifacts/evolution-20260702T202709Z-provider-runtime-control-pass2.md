# Evolution Run: provider-runtime-control pass 2

- Source digest: `github-growth-20260702T202709.417046Z`
- Branch: `codex/blackhole-evolve/20260702T202756.038213-add-or-update-a-bounded-local-skill-route-discov`
- Rollback artifact: `artifacts/rollback-20260702T202709Z-provider-runtime-control-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T202709Z-provider-runtime-control-pass2`
- Theme: `provider-runtime-control`
- Pass: 2 of 4

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: GitHub page exposes `SKILL.md`, `skill.yml`, references, scripts, evals, and a research/advice boundary. Interpreted only as bounded skill-route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: GitHub page describes a general-agent world-model/benchmark project. Interpreted as adjacent `agent_harness_eval_required`, not skill-route activation.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: GitHub page describes autonomous, collaborative, socially intelligent agent work. Interpreted as adjacent general-agent evidence.
- `https://github.com/ksimback/looper`: GitHub page describes review-gated agent loops. Interpreted as adjacent general-agent workflow evidence.

## Hypothesis

Pass 1 made a harmless body-free provider-runtime replay sample visible. Pass 2 should turn that into an operator-visible checkpoint that says whether the current bounded local lane may advance, must be repaired, or needs review, without exposing provider inputs or granting provider launch.

## Change

- Added `provider_runtime_promotion_checkpoint` to `skill_route_discovery_lane` output.
- The checkpoint joins provider-runtime sample-gate status, current-action preflight status, and replay-sample readiness into one body-free supervisor row.
- Added the current digest pass-2 fixture with zhengxi-views as the skill-route row and Qwen-AgentWorld, Fundamental-Ava, and looper as adjacent general-agent rows.
- Updated docs and docs-contract coverage for the checkpoint boundary.
- Left `docs/self-model.md` unchanged. It already states rollback-backed local evolution and does not need a new self-description for this implementation.

## Validation

- `python -m pytest tests/test_harness_eval.py::test_skill_route_discovery_current_digest_20260702T202709_provider_runtime_control_pass2 -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_bounded_matrix` passed.
- `python -m pytest tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs -q` passed.

## Review Notes

- No provider was launched.
- No external harness was executed.
- No upstream repository code was cloned, installed, or run.
- The checkpoint is not promotion authority by itself; it is a body-free replay/readiness row for the external supervisor.
