# Runner Harness Control PR Intake

- Source digest: `github-growth-20260624T063355.562521Z`
- Capability window: `runner-harness-control`, pass 1 of 4
- Rollback ref: `refs/blackhole-rollback/20260624T063355Z-runner-harness-control-pr-intake`
- Rollback artifact: `artifacts/rollback/20260624T063355Z-runner-harness-control-pr-intake.md`

## Evidence Summary

Reviewed the carried public evidence only:

- `https://github.com/omnigent-ai/omnigent` presents a public meta-harness for orchestrating multiple agent harnesses with policies, sandboxing, shared sessions, and testable workflow control surfaces.
- The carried proposal messages emphasized PR migration, duplicate commit/PR signals, and generic or untitled PR handling.

Reusable lesson: PR-driven runner migrations need an intake contract that distinguishes specific, unique PR evidence from duplicate or generic PR noise before final scope and validation gates are recomputed.

## Hypothesis

The existing runner control-plane route already exposes source digest, proposal IDs, evidence hashes, stage diagnostics, replay, recovery, and report artifacts. It did not yet validate PR-event-specific intake. Adding a body-free PR intake sub-contract makes the local migration workflow legible end to end: fixture requirements, deduplication, generic-title handling, final scope, validation gates, replay, and report evidence are all visible without exporting PR titles or URLs.

## Changes

- Extended `agent_workflow_route` intake evaluation with `pull_request_events` and `controller_recomputed` validation.
- Added duplicate PR detection, generic or untitled PR counting, unique usable PR event selection, and recomputed proposal/scope/gate matching.
- Added stage diagnostic counts for total and usable PR events.
- Added a replay fixture for a PR migration intake with one specific event, one duplicate event, and one untitled event.
- Added a focused regression test and updated aggregate local harness eval counts.
- Documented the local PR migration checklist in `docs/architecture.md`.

## Validation

- `pytest tests/test_harness_eval.py -q -k agent_workflow_route_pr_migration_intake`: passed
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`: passed
- `pytest tests/test_harness_eval.py -q`: passed, `147 passed`
- `pytest -q`: passed, `415 passed`

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: apply rollback-backed, locally validated behavior changes when the evidence supports them. The self-model remains behavior-adjacent rather than a permission source.

## Review Notes

- No upstream code, pull request body, install script, provider route, external harness, or remote execution was imported or run.
- Raw PR titles, source URLs, proposal bodies, recovery commands, and artifact paths remain omitted or represented by hashes/counts in structured output.
- Generic or untitled PR events are not treated as unsafe; they are counted and excluded from final-scope recomputation until specific PR evidence exists.
