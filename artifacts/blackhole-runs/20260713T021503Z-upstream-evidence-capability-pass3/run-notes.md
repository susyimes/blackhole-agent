# Run Notes: agent_harness_eval_cluster_local_apply (upstream-evidence-capability pass 3)

- Source digest: github-growth-20260712T181308.938536Z
- Selected proposal: prop-agent-harness-eval-cluster / trend:Tencent-Hunyuan/Hy3-3
- Capability action: apply_one_local_validation_candidate
- Capability theme: upstream-evidence-capability (pass 3 of 4)
- Branch: grok/blackhole-evolve/20260712T181400.643678-build-one-local-agent-harness-evaluation-cluster
- Rollback: artifacts/rollback/20260713T021503Z-rollback-point.md
- Local rollback ref: refs/blackhole/rollback/20260713T021503Z

## Hypothesis

Pass 2 queued general_agent_project rows in `agent_harness_eval_cluster` as
`ready_for_local_comparison`, but operators still lacked an integration path that
evaluates comparison criteria for one selected candidate and unlocks bounded
follow-up lanes. Pass 3 should apply one local validation candidate without
adopting foreign agent behavior or star-count patches.

## Change set

- Added `build_agent_harness_eval_cluster_local_apply` and comparison evaluation
  helpers on `agent_harness_eval_lane`.
- Selected Hy3-style candidate by owner/repo key; privacy agent-chief remains
  review-only and cannot unlock lanes.
- Fixture + regression tests for ready unlock and privacy block.
- Docs and self-model updated for pass 3 continuity.

## Validation

```text
pytest tests/test_harness_eval.py tests/test_docs_contracts.py tests/test_github_growth.py \
  -q -k "agent_harness_eval_cluster or upstream_evidence or local_harness_eval_runs"
```

Result: 13 passed, 406 deselected.

## Review notes

- prop-agent-chief-privacy-review-hold remains review-only; local apply blocks
  selecting privacy-boundary rows.
- prop-skill-route-discovery-cluster deferred; not required to deepen the selected
  harness-eval local-apply path in this pass.
- No runtime_action, provider launch, external harness execution, remote
  execution, or raw evidence URL export was introduced.
