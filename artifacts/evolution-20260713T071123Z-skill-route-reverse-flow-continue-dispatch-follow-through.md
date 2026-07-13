# Evolution: reverse-flow continue dispatch follow-through

Digest: `github-growth-20260713T071123.677935Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: durable follow-through policy + policy-aware follow operator entry

## Hypothesis

Inventory dispatch packaging already exports `action` + `execute_recommended`, but
supervisors still re-derived whether to call dispatch with `execute=True` from
those two fields (and nested wake mode/status). Collapsing inventory into one
`follow_through_action` / `call_dispatch_with_execute` packet, and adding a
policy-aware `follow_*` entry that executes only when the durable recommendation
says so, keeps residual fortress stages subordinate and makes reverse-flow-first
continue legible without enabling activation.

## What changed

1. **`resolve_reverse_flow_focused_validation_continue_dispatch_follow_through`** —
   maps inventory dispatch into:
   - `follow_through_action` (`execute_now` | `wait_for_local_allowlist` |
     `keep_activation_external` | `repair` | `noop`)
   - `call_dispatch_with_execute`
   - residual hold active; residual export always denied
2. **`follow_reverse_flow_focused_validation_continue_dispatch`** —
   preferred policy-aware operator entry:
   - package inventory
   - resolve follow-through
   - call dispatch with execute only when `call_dispatch_with_execute`
   - attach `post_follow_through` after run/record
   - `execute=None` follows recommendation; `execute=False` stays inventory-only
3. **`dispatch_reverse_flow_focused_validation_continue_supervisor_wake`** —
   attaches `follow_through` on inventory paths and
   `follow_through` + `post_follow_through` on `run_and_record`
4. **operator_state** — while reverse-flow focused validation is ready/unrecorded
   (and failed/passed inventory paths):
   - nested `continue_dispatch_follow_through`
   - `continue_dispatch_follow_through_action`
   - `continue_dispatch_call_with_execute`
   - `continue_dispatch_follow_through_helper` + resolve helper
5. **record_helpers / render / docs / self-model** — surface follow-through;
   residual fortress stages stay subordinate until reverse-flow record/close and
   activation-external acceptance.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` — 34 passed.

## Rollback

`refs/blackhole/rollback/20260713T151644Z`

Artifact: `artifacts/rollback-20260713T151644Z.md`

## Self-model

Updated Skill Route Discovery Habit observations for digest
`github-growth-20260713T071123.677935Z` to record dispatch follow-through and
policy-aware follow entry. Self-model remains descriptive, not a permission source.

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied on dispatch/follow surfaces
- Follow/dispatch residual_export_allowed stays false
- rnskill companion and fortress residual harness-eval remain adjacent; fortress
  is not residual-active while reverse-flow waits (0/3 unrecorded)
- Next operator step while reverse-flow focused validation is ready with zero
  partial rows: read `continue_dispatch_follow_through_action=execute_now` /
  `continue_dispatch_call_with_execute=true`, then call
  `follow_reverse_flow_focused_validation_continue_dispatch(pipeline,
  command_runner=...)` (or inventory-only with `execute=False`)
- Next operator step while partial: same path; follow runs remaining units only
  (`mode=record_remaining`)
- After full cover + pass: follow returns `action=run_and_record` with
  `post_follow_through_action=keep_activation_external`; residual fortress
  stages may proceed only after residual-active cascade
