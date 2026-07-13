# Evolution: reverse-flow partial command-hash merge + missing-hash inventory

Digest: `github-growth-20260713T043123.469301Z`
Proposal: `prop-reverse-flow-skill-route-discovery` (bound against lingbol088-spec/reverse-flow-skill; residual fortress adjacent)
Surface: merge partial body-free command-hash results across record wakes + export missing-hash inventory before residual export

## Hypothesis

Reverse-flow focused validation was ready/unrecorded with supervisor_next
`run_focused_local_test_validation_then_keep_activation_external`. Prior work
kept partial rows on ready and claimed they accumulate, but
`record_skill_route_discovery_focused_local_test_validation_results` replaced
prior `command_results` with each new wake. Across multi-wake reverse-flow
continue, partial coverage could never grow to full cover unless a single call
listed every expected hash — residual export stayed blocked indefinitely under
incremental record.

## What changed

1. **`merge_skill_route_discovery_focused_validation_command_results`** — body-free merge of prior + new `{command_hash, passed, in_expected_set}` rows; later same-hash wins; no command text/stdout/URLs.
2. **`missing_skill_route_discovery_focused_validation_command_hashes`** — lists expected hashes still missing from recorded results.
3. **`record_skill_route_discovery_focused_local_test_validation_results`** — merges prior focused_validation.command_results with new rows before rebuild (reverse-flow and residual record paths).
4. **Focused validation packet** — exports `missing_command_hashes` / `missing_command_hash_count` while ready/failed; record_helpers include merge helper.
5. **`operator_state`** — exports `reverse_flow_focused_validation_missing_command_hashes` and count; render surfaces missing hash count; notes that partial rows accumulate via merge.
6. Tests / docs / self-model updated for this run.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k skill_route_discovery
```

Result: **41 passed**.

## Rollback

`refs/blackhole-rollback/20260713T123250Z`

Artifact:
`artifacts/rollback/rollback-point-20260713T123250Z-reverse-flow-partial-merge.md`

## Review notes

- agent-chief remains privacy review-only
- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart stay denied
- residual_export_allowed remains false until reverse-flow record/close covers expected hashes and residual cascade is residual-active
- rnskill companion and fortress residual harness-eval remain adjacent; fortress is not residual-active while reverse-flow waits
- Next operator step while reverse-flow focused validation is ready/unrecorded: run body-free focused commands, record remaining hashes (merge accumulates), or close with outcome when full cover is known
