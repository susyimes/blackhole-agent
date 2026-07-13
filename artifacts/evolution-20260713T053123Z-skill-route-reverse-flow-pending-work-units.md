# Evolution: reverse-flow focused validation pending work units + continue outcomes

Digest: `github-growth-20260713T053123.445910Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: package ordered pending work units (command + hash) and a continue-outcomes record integration seam

## Hypothesis

Continue-plan modes and durable pending command texts already tell supervisors
*what* remains, but run_pending / record_remaining wakes still required re-zipping
`pending_commands` against `missing_command_hashes` and hand-building body-free
record rows. Pairing each pending unit and materializing outcomes from that
inventory closes the operator-visible continue path without residual export or
activation.

## What changed

1. **`pending_skill_route_discovery_focused_validation_work_units`** — ordered
   `{command, command_hash, inventory_index}` pairs for missing hashes only.
2. **`materialize_reverse_flow_focused_validation_continue_record_rows`** —
   body-free rows from hash-map / parallel-bool / row-dict outcomes for pending
   units only.
3. **`record_reverse_flow_focused_validation_continue_outcomes`** — integration
   seam: read continue_plan pending work units → materialize → merge via
   existing record path.
4. **Continue plan / focused validation / operator_state** — export
   `pending_work_units` + counts; record_helpers name the new helpers.
5. **Render / docs / self-model** — note pending work units and continue-outcomes
   path; residual export and activation remain denied.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: 41 passed, 111 deselected.

Also: `pytest tests/test_docs_contracts.py -q` → 34 passed.

## Rollback

`refs/blackhole/rollback/20260713T133238Z`

Artifact: `artifacts/rollback-20260713T133238Z.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied
- residual_export_allowed remains false until reverse-flow record/close covers expected hashes and residual cascade is residual-active
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with zero partial rows: run `continue_plan.pending_work_units` commands, then `record_reverse_flow_focused_validation_continue_outcomes` (or close-with-outcome)
- Next operator step while partial: same path with remaining units only (`mode=record_remaining`)
- After full cover + pass: continue_plan mode becomes keep_activation_external; supervisors may accept activation-external handoff, then residual fortress stages
