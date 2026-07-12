# Run Notes: agent_harness_eval_cluster (upstream-evidence-capability pass 2)

- Source digest: github-growth-20260712T175313.658382Z
- Selected proposal: prop-agent-harness-eval-cluster
- Capability theme: upstream-evidence-capability (pass 2 of 4)
- Branch: grok/blackhole-evolve/20260712T175403.007819-use-reverse-flow-skill-and-rnskill-skill-route-d
- Rollback: artifacts/rollback/20260713T015521Z-rollback-point.json
- Local rollback ref: refs/blackhole/rollback/20260713T015521Z

## Hypothesis

General-agent project signals (agent-chief, Hy3, fortress) should become one
operator-visible local harness-eval cluster with comparison criteria, not
another isolated note. External trends must not auto-open runtime_action;
documentation/test/code_patch unlock only after local comparison; star-count
alone never drafts a behavioral patch; privacy-class agent-chief evidence stays
review-only.

## Change set

- Added `build_agent_harness_eval_cluster` controller surface on
  `agent_harness_eval_lane`
- Documented comparison criteria and star-count insufficiency
- Added fixture + regression test for agent-chief/Hy3/fortress cluster
- Updated architecture, upstream-evidence-interpretation, and self-model docs

## Validation

```text
PYTHONPATH=src python -m pytest \
  tests/test_harness_eval.py::test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs \
  tests/test_harness_eval.py::test_agent_harness_eval_cluster_queues_agent_chief_hy3_fortress_without_runtime_action \
  tests/test_docs_contracts.py::test_architecture_links_upstream_evidence_interpretation_contract \
  tests/test_docs_contracts.py::test_upstream_evidence_interpretation_doc_records_capability_step_contract \
  tests/test_github_growth.py::test_upstream_evidence_capability_step_prefers_pr_compare_and_retains_privacy_boundary \
  tests/test_github_growth.py::test_build_digest_attaches_upstream_evidence_capability_step_for_current_window \
  tests/test_github_growth.py::test_self_evolution_plan_carries_upstream_evidence_capability_step \
  -q
# 7 passed
```

## Review notes

- prop-upstream-evidence-capability-step remains review-only for privacy/offensive boundaries
- agent-chief privacy-leakage rows stay review-only; no raw evidence URL export
- Skill-route discovery proposals deferred; this pass advanced the selected agent_harness_eval cluster step
- No runtime_action, provider launch, remote execution, push, promotion, or restart performed
