# Evolution: reverse-flow focused validation continue plan

Digest: `github-growth-20260713T051123.935613Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: package one inspectable continue wake (`build_reverse_flow_focused_validation_continue_plan`) and export pending command texts + continue_plan mode on durable operator_state

## Hypothesis

Partial supervisor_next promotion, recorded/missing hash inventories, and
pending command counts already support multi-wake reverse-flow continue, but
supervisors still had to re-open nested `focused_validation.commands` to learn
which local commands remain. Zero-row first wakes and partial continue wakes
were also framed as separate work units rather than one pending inventory.
A single continue-plan surface unifies both wakes around `pending_commands` /
`missing_command_hashes` and makes pending command **text** durable on
operator_state without re-rendering markdown.

## What changed

1. **`build_reverse_flow_focused_validation_continue_plan`** — operator-visible
   continue wake packet with modes:
   - `run_pending` (zero-row ready)
   - `record_remaining` (partial ready)
   - `repair` (failed)
   - `keep_activation_external` (passed)
   Residual export stays denied on this surface.
2. **Focused validation attach** — `continue_plan` on the focused validation
   packet and nested under `focused_validation.continue_plan`; named in
   `record_helpers`.
3. **operator_state** — exports
   `reverse_flow_focused_validation_pending_commands` and
   `reverse_flow_focused_validation_continue_plan_mode` alongside existing hash
   inventories and pending counts.
4. **Render** — pipeline markdown includes continue plan mode and notes the
   unified pending-only continue wake helper.
5. Tests / docs / self-model updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

## Rollback

`refs/blackhole-rollback/20260713T131323Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T131323Z-reverse-flow-continue-plan.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied
- residual_export_allowed remains false until reverse-flow record/close covers expected hashes and residual cascade is residual-active
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with zero partial rows: read `continue_plan` / operator_state pending_commands, run those local commands, record body-free hashes (or close with outcome)
- Next operator step while partial: `continue_plan.mode=record_remaining` — run only pending_commands / missing hashes, record via merge
- After full cover + pass: continue_plan mode becomes keep_activation_external; supervisors may accept activation-external handoff, then residual fortress stages
