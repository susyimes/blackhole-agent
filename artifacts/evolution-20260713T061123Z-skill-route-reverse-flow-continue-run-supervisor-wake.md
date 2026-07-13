# Evolution: reverse-flow continue-run supervisor_wake

Digest: `github-growth-20260713T061123.552918Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: resolve reverse-flow-first supervisor_next after continue-run inventory/run before residual stages

## Hypothesis

Continue-run plan/execute/record already runs allowlisted local pytest inventory
units and merges body-free outcomes, but the operator-visible return packet did
not package post-run `supervisor_next`, continue mode, or residual-hold state.
Supervisors still had to re-inspect nested pipeline packets to know whether to
run remaining units, keep activation external, or unlock residual fortress
stages. Packaging an inspectable supervisor_wake after inventory or run/record
keeps residual stages blocked until reverse-flow record/close and
activation-external acceptance.

## What changed

1. **`resolve_reverse_flow_focused_validation_continue_run_supervisor_wake`** —
   packages mode, status, residual hold, handoff/acceptance status, and
   reverse-flow-first `supervisor_next` from continue-plan / run-plan /
   run-result / post-record pipeline without executing commands or enabling
   activation.
2. **`run_reverse_flow_focused_validation_continue_pending_work_units`** —
   attaches `supervisor_wake` and top-level supervisor/continue/handoff fields
   on the run-and-record return packet.
3. **operator_state** — while reverse-flow focused validation is ready/unrecorded:
   - always prefers continue supervisor resolver (zero-row and partial)
   - exports `reverse_flow_focused_validation_continue_run_executable`
   - exports `reverse_flow_focused_validation_continue_runnable_work_unit_count`
4. **docs / self-model / render helpers** — surface the wake resolver; residual
   export and activation remain denied on continue-run surfaces.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` — 34 passed.

## Rollback

`refs/blackhole/rollback/20260713T061508Z`

Artifact: `artifacts/rollback-20260713T061508Z.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied on continue-run surfaces
- Continue-run residual_export_allowed stays false on the wake surface; pipeline residual_export_allowed is informational only via `pipeline_residual_export_allowed`
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with zero partial rows: call `run_reverse_flow_focused_validation_continue_pending_work_units(pipeline, command_runner=...)` then read `supervisor_wake`
- Next operator step while partial: same path with remaining units only (`mode=record_remaining`)
- After full cover + pass: `supervisor_wake.mode=keep_activation_external`, handoff ready / acceptance accepted; residual fortress stages may proceed only after residual-active cascade
