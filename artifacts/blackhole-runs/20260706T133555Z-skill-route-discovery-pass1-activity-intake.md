# Blackhole Run: skill-route-discovery pass 1 activity intake

- Source digest: `github-growth-20260706T133555.891986Z`
- Branch: `codex/blackhole-evolve/20260706T133653.593174-document-a-bounded-skill-route-discovery-lane-fo`
- Rollback artifact: `artifacts/rollback/20260706T133653.593174.md`
- Rollback ref: `refs/blackhole-rollback/20260706T133653.593174`
- Self-model: read and left unchanged. The current preference already supports rollback-backed, locally validated behavior changes, and this run had stronger evidence for a harness-lane behavior surface than for revising self-description text.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, scripts, local sandbox and CTF framing, install examples, and staged reverse-analysis workflow. Treated as bounded `skill_route_discovery` evidence only.
- `https://github.com/shepherd-agents/shepherd`: public agent runtime substrate describing reversible execution traces, fork/replay/revert, and runtime supervision. Treated as `agent_harness_eval_required`.
- `https://github.com/shepherd-agents/shepherd/pull/24`: merged July 6, 2026 PR for controller extraction plus strict typecheck gate, with verification notes. Treated as activity-shape evidence for local harness evaluation.
- `https://github.com/InternScience/Agents-A1`: general long-horizon agent/model project evidence. Treated as `agent_harness_eval_required`.

## Hypothesis

General agent-project and upstream PR activity should not inherit skill-route lanes or produce direct behavior changes. A body-free `activity_intake_panel` on `agent_harness_eval_lane` makes trend, push, issue-comment, opened-PR, and merged-PR shapes operator-visible before any documentation, test, or code_patch follow-up is considered.

## Local Change

- Added `activity_intake_panel` to `agent_harness_eval_lane`.
- Added canonical activity event-kind normalization for repository trend, push, issue-comment, opened PR, merged PR, and fork rows.
- Added `agent_harness_eval_lane_20260706T133555_activity_shapes.json` with current wake evidence and assertions that direct behavior change, external harness execution, provider launch, remote execution, raw URLs, and raw activity bodies stay denied.
- Updated `docs/skill-route-discovery.md` with the current pass-1 interpretation and replay command.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "20260706T133555 or local_harness_eval_runs_pass"`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane"`: passed.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed.

## Review Notes

- No upstream repository was cloned, installed, imported, or executed.
- No external harness, provider runtime, remote execution, skill activation, or restart path was enabled.
- The panel records source URL hashes and item IDs only; raw source URLs and upstream bodies remain excluded from structured harness outputs.
