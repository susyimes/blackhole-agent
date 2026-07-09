# Skill Route Discovery Pass 1

- Source digest: github-growth-20260709T061527.151662Z
- Theme: skill-route-discovery
- Rollback artifact: artifacts/rollback/20260709T061622Z-skill-route-discovery-pass1/rollback-point.md
- Rollback ref: refs/blackhole-agent/rollback/20260709T061622Z-skill-route-discovery-pass1

## Evidence Review

Reviewed only the carried proposal evidence URLs. `reverse-flow-skill` presents a Codex/AI Agent skill package with `skills/reverse-flow`, SKILL.md-oriented workflow language, sandbox framing, and install/run pressure. `rnskill` presents a generic AI Agent Skills collection for Codex, Claude Code, and SKILL.md-compatible project skills. `agent-chief` and `Hy3` are general agent/model projects rather than direct skill-route packages.

## Local Change

Added `current_digest_20260709T061527_pass1_validation_lane` to the skill-route lane map and harness eval output. The lane routes reverse-flow through the test lane, rnskill through the documentation lane, and keeps agent-chief/Hy3 behind `agent_harness_eval_required` with no direct pre-eval implementation lane.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The existing self-model already says to prefer rollback-backed, locally validated behavior changes over validation-report-only evolution.

## Validation

Focused replay passed:

```powershell
python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260709T061527
```

Result: 2 passed, 724 deselected.
