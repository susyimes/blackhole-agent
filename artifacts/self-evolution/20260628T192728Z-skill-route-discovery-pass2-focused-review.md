# Skill Route Discovery Pass 2 Focused Review

- Source digest: `github-growth-20260628T192730.399337Z`
- Capability window: `skill-route-discovery`, pass 2 of 4
- Branch: `codex/blackhole-evolve/20260628T192825.547376-create-a-local-validation-lane-for-generic-skill`
- Rollback ref: `refs/rollback/20260628T192728Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260628T192728Z-skill-route-discovery-pass2.txt`
- Evidence URLs: `https://github.com/lyra81604/zhengxi-views`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/majidmanzarpour/threejs-game-skills`

## Hypothesis

The active pass-2 proposal mix needs an operator-visible focused review lane
that binds current proposal IDs directly to bounded local validation rows.
Generic `SKILL.md` workflow repositories should enter only documentation,
config, test, or code_patch lanes, while adjacent general-agent benchmark
projects must remain in `agent_harness_eval_required` until a local harness
evaluation route is complete.

## Change

- Added `focused_evidence_review_lane` under
  `current_digest_pass2_local_validation_lane`.
- Added active proposal IDs for `p1-skill-route-discovery-generic`,
  `p2-agent-harness-eval-qwen-agentworld`, and
  `p3-game-frontend-skill-route`.
- Added a frozen fixture for source digest
  `github-growth-20260628T192730.399337Z`.
- Documented the pass-2 focused review behavior and kept Qwen-AgentWorld out of
  skill-route inheritance.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The current self-model already favors
rollback-backed local evolution with a narrow safety boundary, and this run had
a concrete behavior path to improve instead of a self-description-only update.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass2"
python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane"
python -m pytest tests/test_skill_routing.py -q
```

Results: 2 passed, 10 passed, and 87 passed respectively.

The packet remains body-free and denies runtime action, upstream skill or agent
activation, external harness execution, provider launch, remote execution,
profile writes, memory writes, raw source URL export, raw evidence URL export,
target path export, replay-command export, and upstream body export.
