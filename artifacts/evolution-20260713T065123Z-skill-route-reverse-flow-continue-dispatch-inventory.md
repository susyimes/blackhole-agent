# Evolution: reverse-flow continue dispatch inventory packaging

Digest: `github-growth-20260713T065123.898754Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: durable inventory dispatch packet + dispatch post_dispatch_inventory

## Hypothesis

`dispatch_reverse_flow_focused_validation_continue_supervisor_wake` is already the preferred single operator entry, but operator_state only named the helper and nested the inventory wake. Supervisors still re-derived dispatch `action` / execute recommendation / residual-export denial from nested wake fields. Packaging a body-free inventory dispatch packet on operator_state (and reusing it inside dispatch) keeps residual fortress stages subordinate and makes reverse-flow-first continue legible without re-resolving nested packets or enabling activation.

## What changed

1. **`package_reverse_flow_focused_validation_continue_dispatch_inventory`** —
   packages body-free inventory dispatch without running commands:
   - `action` (`inventory_only` | `inventory_not_executable` | `repair` |
     `keep_activation_external` | `noop`)
   - `execute_recommended` when local pytest units are allowlisted
   - residual hold active; residual export always denied on this surface
   - no stdout, activation, push, promotion, provider launch, remote apply,
     external skill execution, or kernel restart
2. **`dispatch_reverse_flow_focused_validation_continue_supervisor_wake`** —
   - inventory-only path returns the packager packet
   - `run_and_record` attaches `inventory_dispatch` + `post_dispatch_inventory`
     so the next durable action is inspectable after execute
3. **operator_state** — while reverse-flow focused validation is ready/unrecorded
   (and failed/passed inventory paths):
   - nested `reverse_flow_focused_validation_continue_dispatch` (no pipeline snapshot)
   - `continue_dispatch_action`
   - `continue_dispatch_execute_recommended`
   - `continue_dispatch_helper` + `continue_dispatch_inventory_helper`
4. **record_helpers / render / docs / self-model** — surface the inventory packager;
   residual fortress stages stay subordinate until reverse-flow record/close and
   activation-external acceptance.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` — full docs contracts suite.

## Rollback

`refs/blackhole/rollback/20260713T065347Z`

Artifact: `artifacts/rollback-20260713T065347Z.md`

## Self-model

Updated Skill Route Discovery Habit observations for digest
`github-growth-20260713T065123.898754Z` to record inventory dispatch packaging
and durable operator_state dispatch fields. Self-model remains descriptive, not
a permission source.

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied on dispatch surfaces
- Dispatch residual_export_allowed stays false; pipeline residual_export_allowed
  remains informational only via nested wake `pipeline_residual_export_allowed`
- rnskill companion and fortress residual harness-eval remain adjacent; fortress
  is not residual-active while reverse-flow waits (0/3 unrecorded)
- Next operator step while reverse-flow focused validation is ready with zero
  partial rows: read `continue_dispatch_action=inventory_only` /
  `continue_dispatch_execute_recommended=true`, then call
  `dispatch_reverse_flow_focused_validation_continue_supervisor_wake(pipeline,
  command_runner=...)` (or inventory-only with `execute=False`)
- Next operator step while partial: same path; dispatch runs remaining units only
  (`mode=record_remaining`)
- After full cover + pass: dispatch returns `action=run_and_record` with
  `post_dispatch_inventory.action=keep_activation_external`; residual fortress
  stages may proceed only after residual-active cascade
