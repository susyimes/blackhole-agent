# Evolution Run: skill-route-discovery pass 1

Source digest: `github-growth-20260706T225555.484632Z`

## Evidence

- `https://github.com/shepherd-agents/shepherd`: inspected as public meta-agent/runtime substrate evidence with reversible traces, replay, supervision, retained outputs, sandbox or workspace review claims, and benchmark/evaluation pressure.
- `https://github.com/shepherd-agents/shepherd/pull/30`: treated as benchmark/meta-agent workflow pressure, not as a runtime dependency.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: retained as explicit skill/workflow route evidence for the active window; install/run pressure remains diagnostic only.
- `https://github.com/InternScience/Agents-A1`: retained as adjacent general-agent project evidence requiring local harness evaluation before behavior adoption.

## Hypothesis

Benchmark-style and meta-agent trend evidence should create a deterministic local probe lane before runtime integration. The lane should require benchmark tasks, evaluation dimensions, an expected measurable outcome, complete project probe fields, and side-effect denial, while preserving the existing `agent_harness_eval_required` gate for broader general-agent projects.

## Changes

- Added `benchmark_meta_agent_probe_lane` to `agent_harness_eval_lane`.
- Added a local fixture for the current Shepherd-inspired benchmark/meta-agent probe.
- Added a focused regression and updated aggregate local harness fixture counts.
- Documented the pass-1 probe lane in `docs/skill-route-discovery.md`.

## Rollback

- Rollback ref: `refs/blackhole/rollback/20260706T225554Z`
- Rollback artifact: `artifacts/rollback/20260706T225554Z-skill-route-discovery-pass1-agent-harness-benchmark-probe/rollback-point.md`

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k benchmark_meta_agent_probe`: passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or local_harness_eval_runs"`: passed, 9 tests.
- `python -m pytest tests/test_harness_eval.py -q`: passed, 248 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 12 tests.

## Review Notes

- Self-model was read and left unchanged. It already prefers rollback-backed, locally validated behavior paths over validation-report-only changes.
- No upstream code, skill body, install command, provider launch, external harness execution, or remote execution path was adopted.
- Ad hoc Python imports outside pytest resolved to the parent repository in this environment; pytest uses `tests/conftest.py` to pin this worktree's `src` and is the reported validation path.
