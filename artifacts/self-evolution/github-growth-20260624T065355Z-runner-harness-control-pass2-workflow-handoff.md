# Runner Harness Control Pass 2 Workflow Handoff

- Source digest: `github-growth-20260624T065355.575651Z`
- Capability window: `runner-harness-control`, pass 2 of 4
- Rollback ref: `refs/blackhole-rollback/20260624T145519Z`
- Rollback artifact: `artifacts/rollback-20260624T145519Z.md`

## Evidence Summary

Reviewed the carried proposal context and local prior pass artifacts. The relevant reusable lesson is that a runner workflow should be legible as one replayable control-plane handoff from source intake through mid-flight state, recovery, replay, and report artifacts, without exporting upstream bodies, commands, or paths.

## Hypothesis

`agent_workflow_route` already emitted each control-plane stage separately, but an operator still had to reconstruct the end-to-end handoff from scattered fields. A single body-free `workflow_handoff` packet should make the route easier to replay and recover while preserving the existing privacy and no-external-execution boundary.

## Changes

- Added `control_plane.workflow_handoff` for `agent_workflow_route`.
- The handoff orders intake, midflight, recovery, replay, and report stages; records ready and blocked counts; summarizes source intake, mid-flight state, recovery, replay, and report artifacts; and repeats blocked-stage reasons.
- Extended focused control-plane tests and the pass-2 fixture assertions.
- Documented the field in `docs/architecture.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "agent_workflow_route_control_plane or local_harness_eval_runs"`: passed, 2 tests.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed.
- `python -m pytest tests/test_harness_eval.py -q`: passed, 147 tests.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already supports rollback-backed, locally validated behavior changes outside the narrow safety boundary. This run's durable improvement is the executable handoff contract.

## Review Notes

- No upstream code, provider, external harness, remote execution, or skill installation was run.
- The new handoff exports counts, booleans, hashes, stage names, action codes, and blocker reasons only.
- Raw evidence URLs, recovery commands, report bodies, artifact paths, PR titles, and local rollback refs remain omitted or hashed in evaluator output.
