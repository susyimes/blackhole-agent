# Skill route residual unlocked local lane apply

- Digest: `github-growth-20260712T231308.528323Z`
- Branch: `grok/blackhole-evolve/20260712T231355.463234-run-skill-route-discovery-for-lingbol088-spec-re`
- Proposal track: `prop-residual-adjacent-fortress-harness-eval`
- Rollback: `artifacts/rollback/rollback-point-20260712T231434Z-residual-adjacent-unlocked-local-lane-apply.md`
- Local rollback ref: `refs/blackhole-rollback/skill-route-residual-unlocked-lane-20260712T231434Z`

## Hypothesis

After residual fortress/Hy3 harness local comparison unlocks documentation/test/code_patch, the pipeline should package supervisor next action `apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external` into an operator-visible residual apply surface rather than re-emitting residual comparison notes. Prefer local `test` first for focused validation without inheriting reverse-flow skill unlocks.

## Change

Added `skill_route_discovery_residual_adjacent_unlocked_local_lane_apply`:

1. Consumes ready residual harness local comparison
2. Unlocks only documentation/test/code_patch post-compare lanes
3. Selects preferred focused lane: test → documentation → code_patch
4. Exports body-free command hashes only
5. Keeps skill unlocks closed and activation external

## Validation

```text
pytest tests/test_github_growth.py -q -k "skill_route_discovery_focused_local_test_validation_after_unlocked_apply or skill_route_discovery_residual_adjacent or skill_route_discovery_unlocked_local_test_lane_apply or skill_route_discovery_capability_pipeline"
# 9 passed

pytest tests/test_docs_contracts.py tests/test_github_growth.py -q -k "skill_route or self_model or residual_adjacent"
# 51 passed

pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply
# 6 passed
```

## Files

- `src/blackhole_agent/github_growth.py`
- `tests/test_github_growth.py`
- `docs/skill-route-discovery.md`
- `docs/self-model.md`
- rollback + this artifact

## Review notes

- Activation, push, promotion, provider launch, remote apply, external skill execution, and kernel restart remain denied
- agent-chief privacy review-only unchanged
- Residual skill unlock inheritance remains false
- Next supervisor action after ready residual unlocked apply: focused residual local validation while activation stays external
