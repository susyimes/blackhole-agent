# Evolution: residual adjacent focused validation activation-external handoff

Digest: `github-growth-20260713T010202.728081Z`
Proposal: `prop-fortress-residual-adjacent-harness-eval` (after residual focused validation)
Surface: `skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`

## Hypothesis

After residual adjacent focused local validation records a body-free command-hash
pass, the pipeline still lacked an operator-visible activation-external handoff
for that residual lane. Reverse-flow already has
`skill_route_discovery_focused_validation_activation_external_handoff`; residual
should mirror that without inheriting reverse-flow skill unlocks, while noting
any remaining residual fortress/Hy3 proposal IDs for continuity.

## What changed

- New controller surface
  `skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`
- Ready decision:
  `package_activation_external_handoff_after_residual_adjacent_focused_validation_pass`
- Supervisor next on ready with no remaining residual rows:
  `keep_activation_external_after_residual_adjacent_focused_local_validation`
- Supervisor next on ready with remaining residual rows:
  `keep_activation_external_and_note_remaining_residual_adjacent_rows`
- Remaining residual IDs exported as body-free
  `remaining_residual_adjacent_proposal_ids`
- Wired through capability pipeline builder, reverse-flow record refresh,
  residual focused record/close refresh, operator render, docs, self-model, and tests
- Skill unlocks stay closed; activation/push/promotion/provider/remote/restart stay denied

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply tests/test_github_growth.py::test_skill_route_discovery_residual_adjacent_harness_eval_local_apply_prefers_fortress tests/test_docs_contracts.py -q -k "architecture_links_upstream or skill_route_discovery_doc_records_capability"
```

Result: passed (focused residual path + residual fortress prefer + docs contracts).

## Rollback

`refs/blackhole-agent/rollback/20260713T010330Z-residual-adjacent-focused-validation-activation-external-handoff`

Artifact:
`artifacts/rollback/rollback-point-20260713T010330Z-residual-adjacent-focused-validation-activation-external-handoff.md`

## Review notes

- agent-chief remains privacy review-only
- Residual activation-external handoff is distinct from reverse-flow activation-external handoff
- Remaining residual Hy3 continuity is noted, not auto-selected or unlocked
- No activation, push, promotion, provider launch, remote apply, external skill execution, or kernel restart from this surface
