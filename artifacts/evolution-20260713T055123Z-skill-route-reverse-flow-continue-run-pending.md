# Evolution: reverse-flow focused validation continue run-and-record

Digest: `github-growth-20260713T055123.668432Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: package + execute allowlisted local pending work units and record body-free outcomes

## Hypothesis

Continue-plan modes and ordered `pending_work_units` already tell supervisors
*what* remains, and `record_reverse_flow_focused_validation_continue_outcomes`
already merges body-free rows — but run_pending / record_remaining wakes still
required an external step to actually execute inventory commands. Packaging a
local-only run plan, executing allowlisted pytest inventory lines, and recording
outcomes closes the operator-visible continue path without residual export or
activation.

## What changed

1. **`reverse_flow_focused_validation_continue_local_command_allowed`** — admits
   only local pytest inventory lines targeting `tests/` with no shell
   metacharacters (not a general command executor).
2. **`build_reverse_flow_focused_validation_continue_run_plan`** — annotates each
   pending unit with `local_allowed` / `skip_reason` for inspectable
   run_pending and record_remaining wakes without executing.
3. **`execute_reverse_flow_focused_validation_continue_run_plan`** — runs allowed
   units via injected `command_runner` (no shell, no stdout export) and returns
   body-free `{command_hash → passed}` outcomes plus unit_results.
4. **`run_reverse_flow_focused_validation_continue_pending_work_units`** —
   operator-visible run-and-record seam: build plan → execute pending units →
   record via existing continue-outcomes path.
5. **record_helpers / render / docs / self-model** — surface the new helpers;
   residual export and activation remain denied on the continue-run surfaces.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` — 34 passed.

## Rollback

`refs/blackhole/rollback/20260713T055258Z`

Artifact: `artifacts/rollback-20260713T055258Z.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied on continue-run surfaces
- Continue-run is not a general shell executor; non-pytest / metacharacter commands are skipped without outcomes
- residual_export_allowed on the pipeline may release only after reverse-flow record/close completes residual-active cascade; run_plan/run_result keep residual_export_allowed=false
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with zero partial rows: call `run_reverse_flow_focused_validation_continue_pending_work_units(pipeline, command_runner=...)` (or build/execute/record manually)
- Next operator step while partial: same path with remaining units only (`mode=record_remaining`)
- After full cover + pass: continue_plan mode becomes keep_activation_external; supervisors may accept activation-external handoff, then residual fortress stages
