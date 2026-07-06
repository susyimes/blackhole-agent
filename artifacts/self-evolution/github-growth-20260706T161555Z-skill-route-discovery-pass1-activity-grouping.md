# Skill Route Discovery Pass 1 Activity Grouping

- Source digest: `github-growth-20260706T161555.662839Z`
- Branch: `codex/blackhole-evolve/20260706T161710.169594-add-or-run-a-bounded-skill-route-discovery-valid`
- Rollback point: `artifacts/rollback/20260706T161555Z-skill-route-discovery-pass1-current-window/rollback-point.md`
- Rollback ref: `refs/rollback/20260706T161555Z-skill-route-discovery-pass1-current-window`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex / AI Agent skill workflow with `skills/reverse-flow`, install commands, scripts, and local CTF / sandbox reverse-analysis framing. Interpreted as skill-route evidence only.
- `https://github.com/InternScience/Agents-A1`: general-agent project evidence requiring harness evaluation before implementation.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark / world-model evidence requiring harness evaluation before implementation.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: autonomous collaborative agent evidence requiring harness evaluation before implementation.
- `https://github.com/shepherd-agents/shepherd`: reversible agent runtime substrate evidence with active project movement. Treated as agent-harness evidence, not a direct local runtime adoption route.

## Hypothesis

Multiple activity records from one upstream general-agent project should not multiply implementation pressure. Trend, push, and pull-request movement can improve freshness, but low-detail pushes and untitled PRs should remain one grouped `agent_harness_eval_required` candidate until local harness evidence passes.

## Change

- Added `project_activity_groups` to the agent-harness activity intake panel.
- Activity rows now include a hashed normalized project key and a `low_detail_activity` marker.
- Group rows report raw event count, event kinds, trend count, low-detail count, weighted activity score, and capped project weight.
- Direct behavior change, external harness execution, provider launch, remote execution, raw URL export, and raw body export remain disabled.
- Added a current-window Shepherd regression fixture proving a trend plus low-detail push and untitled merged PR stays grouped as one harness-eval candidate.
- Documented the activity grouping contract in `docs/architecture.md`.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference for reversible local evolution, bounded validation, and no direct activation from public trend evidence matched this run's evidence and change.

## Validation

- `pytest tests/test_harness_eval.py -q -k "low_detail_activity or records_current_activity_shapes"`: passed, 2 tests.
- `pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane"`: passed, 6 tests.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane"`: passed, 10 tests.
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures"`: passed, 1 test.
- `pytest tests/test_docs_contracts.py -q`: passed, 11 tests.

## Review Notes

- The grouping weights are conservative heuristics: repository trend events count more than low-detail push or PR events, and project weight is capped for operator visibility. They do not authorize code patches or runtime adoption.
- Item IDs remain visible for traceability and may include repository-shaped text, but raw source URLs and activity bodies are not exported.
- Reverse-flow evidence remains bounded to documentation, config, test, or code_patch lanes; no upstream skill installation or execution was performed.
