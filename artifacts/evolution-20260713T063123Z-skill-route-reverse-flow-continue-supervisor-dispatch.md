# Evolution: reverse-flow continue supervisor dispatch

Digest: `github-growth-20260713T063123.715169Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: single operator entry that inventories, optionally runs/records, and always returns reverse-flow-first supervisor_wake

## Hypothesis

Continue-run plan/execute/record and post-run supervisor_wake already exist, but
supervisors still needed two steps (run pending units, then read wake) and
operator_state only exported bare executability flags. A single dispatch surface
plus durable inventory wake on operator_state keeps residual fortress stages
blocked until reverse-flow record/close and activation-external acceptance, and
makes the preferred next action inspectable without re-resolving nested packets.

## What changed

1. **`dispatch_reverse_flow_focused_validation_continue_supervisor_wake`** —
   preferred single operator entry:
   - always resolves inventory `supervisor_wake`
   - when `execute=True` and `continue_run_executable`, runs allowlisted pending
     units and optionally records body-free outcomes
   - always returns reverse-flow-first `supervisor_wake` /
     `supervisor_next_action`
   - residual export and activation stay denied on the dispatch surface
2. **operator_state** — while reverse-flow focused validation is ready/unrecorded
   (and failed/passed inventory paths):
   - exports `reverse_flow_focused_validation_continue_run_recommended`
   - exports nested inventory
     `reverse_flow_focused_validation_continue_supervisor_wake`
   - exports
     `reverse_flow_focused_validation_continue_dispatch_helper=dispatch_reverse_flow_focused_validation_continue_supervisor_wake`
3. **record_helpers / render / docs / self-model** — surface the dispatch helper
   as the preferred continue entry; residual fortress stages stay subordinate.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` — 34 passed.

## Rollback

`refs/blackhole/rollback/20260713T143334Z`

Artifact: `artifacts/rollback-20260713T143334Z.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied on dispatch surfaces
- Dispatch residual_export_allowed stays false; pipeline residual_export_allowed remains informational only via nested wake `pipeline_residual_export_allowed`
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with zero partial rows: call `dispatch_reverse_flow_focused_validation_continue_supervisor_wake(pipeline, command_runner=...)` (or inventory-only with `execute=False`)
- Next operator step while partial: same path; dispatch runs remaining units only (`mode=record_remaining`)
- After full cover + pass: dispatch returns `action=keep_activation_external` / `run_and_record` with handoff ready / acceptance accepted; residual fortress stages may proceed only after residual-active cascade
