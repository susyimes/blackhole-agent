# Skill Route Discovery Pass 3 Acceptance Lane

Source digest: `github-growth-20260628T102729.741495Z`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public agent skill shape with `SKILL.md`, references, evals, scripts, and advice-boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public game/frontend skill workflow shape with `skills/`, scripts, scaffold/QA language, and optional asset/provider pressure.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/evaluation project shape, not a skill workflow route.

## Hypothesis

Pass 3 should expose an acceptance surface for the already-built current-run validation lane so a supervisor can see which gates are satisfied before pass 4 without inferring them from raw row fields.

## Change

Added `current_run_pass3_acceptance_lane` to the skill-route proposal lane map. It is derived from `current_run_pass3_validation_lane` and checks:

- Skill-route rows remain in documentation, config, test, or code_patch lanes.
- Selected evidence and validation gates are present.
- Local validation remains required.
- Runtime action, upstream skill/agent activation, external harness execution, provider launch, remote execution, and raw source/evidence/target/upstream/replay-command exports remain denied.
- Adjacent general-agent rows remain `agent_harness_eval_required` and do not inherit skill-route authority.

## Rollback

Rollback artifact: `artifacts/rollback/20260628T102832Z-skill-route-discovery-pass3-current-run.txt`

Rollback ref: `refs/rollback/20260628T102832Z-skill-route-discovery-pass3-current-run`

## Validation

Focused command:

```text
pytest tests/test_skill_routing.py -q -k "current_run_pass3_acceptance_lane or current_run_pass3_validation_lane or current_active_pass2_proposal_lane"
```

Result: passed, 3 tests.

Full command:

```text
pytest -q
```

Result: passed, 479 tests.

## Review Notes

The self-model was left unchanged. This run did not need a new preference statement; the repository already encoded the preference for validated local behavior over report-only scaffolding.
