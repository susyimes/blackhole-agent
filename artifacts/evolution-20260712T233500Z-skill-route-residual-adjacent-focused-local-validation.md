# Evolution: residual adjacent focused local validation

Digest: `github-growth-20260712T233308.367716Z`
Proposal: `prop-fortress-residual-adjacent-harness-eval` (after residual unlocked apply)
Surface: `skill_route_discovery_residual_adjacent_focused_local_validation`

## Hypothesis

After residual adjacent harness comparison unlocks documentation/test/code_patch and
residual unlocked local lane apply packages a preferred focused lane (test-first),
the pipeline still lacked an operator-visible body-free focused validation record/
close surface for that residual lane. Reverse-flow already has
`skill_route_discovery_focused_local_test_validation`; residual should mirror that
without inheriting reverse-flow skill unlocks.

## What changed

- New controller surface
  `skill_route_discovery_residual_adjacent_focused_local_validation`
- Ready decision:
  `run_residual_adjacent_focused_local_validation_with_body_free_command_hashes`
- Pass decision:
  `record_residual_adjacent_focused_local_validation_pass_and_keep_activation_external`
- Supervisor next on ready:
  `run_focused_local_validation_for_residual_adjacent_unlocked_lane_and_keep_activation_external`
- Supervisor next on pass:
  `keep_activation_external_after_residual_adjacent_focused_local_validation`
- Record/close helpers:
  `record_skill_route_discovery_residual_adjacent_focused_local_validation_results`,
  `close_skill_route_discovery_residual_adjacent_focused_local_validation_with_outcome`
- Wired through capability pipeline builder (optional
  `residual_focused_validation_command_results`), reverse-flow record refresh,
  operator render, docs, self-model, and tests
- Skill unlocks stay closed; activation/push/promotion/provider/remote/restart stay denied

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py::test_skill_route_discovery_focused_local_test_validation_after_unlocked_apply tests/test_github_growth.py::test_skill_route_discovery_residual_adjacent_harness_eval_local_apply_prefers_fortress tests/test_docs_contracts.py::test_architecture_links_upstream_evidence_interpretation_contract tests/test_docs_contracts.py::test_skill_route_discovery_doc_records_capability_pipeline_pass1 -q
```

Result: passed.

Broader related filter also passed for skill-route capability / unlocked / focused /
residual / adjacent surfaces.

## Rollback

`refs/blackhole-agent/rollback/20260712T233429Z-residual-adjacent-focused-local-validation`

Artifact: `artifacts/rollback-20260712T233429Z-residual-adjacent-focused-local-validation.md`

## Review notes

- agent-chief remains privacy review-only
- Residual focused validation is distinct from reverse-flow focused local test validation
- Optional selected-step adjacent harness-eval handoff remains available when the selected step is fortress/Hy3 itself
- No activation, push, promotion, provider launch, remote apply, external skill execution, or kernel restart from this surface
