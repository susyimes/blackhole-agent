# Evolution: reverse-flow partial continue supervisor_next + pending inventory

Digest: `github-growth-20260713T045123.532400Z`
Proposal: `prop-reverse-flow-skill-route-discovery-continue` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: promote operator-visible supervisor_next to record-remaining on partial body-free coverage; export recorded/pending inventories

## Hypothesis

Partial body-free command-hash merge and missing-hash inventory already let
multi-wake reverse-flow continue accumulate coverage, but operator-visible
`supervisor_next_action` still said
`run_focused_local_test_validation_then_keep_activation_external` after partial
rows were recorded. That re-advertised a full focused re-run, diluting
reverse-flow-first continue and risking re-execution of already-covered hashes.
Only the secondary `reverse_flow_continue_decision` said record-remaining.

## What changed

1. **`resolve_reverse_flow_focused_validation_continue_supervisor_next`** — zero partial → run full focused set; partial ready → `record_remaining_reverse_flow_focused_validation_command_hashes_then_keep_activation_external`; failed → repair.
2. **`recorded_skill_route_discovery_focused_validation_command_hashes`** / **`pending_skill_route_discovery_focused_validation_commands`** — body-free recorded inventory + map missing hashes back to local command text for continue wakes.
3. **Focused validation ready+partial** — decision
   `record_remaining_focused_validation_command_hashes_before_activation_external`;
   supervisor_next record-remaining; exports `recorded_command_hashes` and
   `pending_commands`.
4. **Blocked handoff / acceptance / residual queue** — inherit record-remaining
   continue action while reverse-flow waits so residual repair noise cannot
   outrank reverse-flow multi-wake continue.
5. **operator_state** — exports recorded/pending inventories; forces
   supervisor_next to record-remaining while partial ready/unrecorded.
6. Tests / docs / self-model updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

## Rollback

`refs/blackhole-rollback/20260713T125315Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T125315Z-reverse-flow-partial-supervisor-next.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied
- residual_export_allowed remains false until reverse-flow record/close covers expected hashes and residual cascade is residual-active
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready with partial rows: run only pending_commands / missing hashes, record via merge, or close with outcome when full cover is known
- Next operator step while ready with zero partial rows: run focused local test validation then keep activation external
