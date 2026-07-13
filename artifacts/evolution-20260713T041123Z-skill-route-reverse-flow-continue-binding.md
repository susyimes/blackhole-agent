# Evolution: reverse-flow continue binding + partial command-hash retention

Digest: `github-growth-20260713T041123.699547Z`
Proposal: `prop-reverse-flow-skill-route-discovery` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: reverse-flow evidence binding on operator_state + partial body-free command-hash retention before residual export

## Hypothesis

After durable operator_state landed, reverse-flow continue still lacked:
1. an explicit body-free bind of reverse-flow selection to reverse-flow-skill evidence markers
2. a machine-readable residual_export_allowed gate
3. retention of partial command-hash results on ready so supervisors can accumulate coverage without re-exporting command text/stdout or prematurely exporting residual fortress IDs

## What changed

1. **Partial body-free results on ready** — `build_skill_route_discovery_focused_local_test_validation` keeps `command_results` while status is `ready`; adds `partial_results_recorded` when coverage is incomplete. Residual hold stays active until full cover/pass or fail.
2. **`_resolve_reverse_flow_evidence_binding`** — body-free bind of selected reverse-flow proposal to `lingbol088-spec/reverse-flow-skill` / `codex_workflow_gate` without raw evidence URLs.
3. **`resolve_skill_route_discovery_pipeline_operator_state`** — exports:
   - `reverse_flow_bound` / `reverse_flow_bound_proposal_id` / `reverse_flow_bound_source_marker`
   - nested `reverse_flow_evidence_binding`
   - `residual_export_allowed` (false while reverse-flow holds residual export)
   - partial coverage counts + `reverse_flow_focused_validation_partial_results_recorded`
   - continue decision `record_remaining_reverse_flow_focused_validation_command_hashes_before_residual_export` when partial rows exist
4. **Render** surfaces binding, residual_export_allowed, and partial coverage.
5. Tests / docs / self-model updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: **41 passed**.

## Rollback

`refs/blackhole-rollback/20260713T121417Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T121417Z-reverse-flow-continue-binding.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active until reverse-flow record/close clears holds and residual cascade is residual-active
- Next operator step while reverse-flow focused validation is ready/unrecorded: run body-free focused commands then `record_skill_route_discovery_focused_local_test_validation_results` (partial rows accumulate) or `close_skill_route_discovery_focused_local_test_validation_with_outcome`
