# Skill Route Discovery Pass 4 Run Note

- Source digest: `github-growth-20260709T001850.976378Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/blackhole-agent/20260709T001848Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260709T001848Z-skill-route-discovery-pass4.md`

## Evidence Reviewed

- `Pluviobyte/rnskill`: public SKILL.md-compatible agent skill collection with docs, tools, plugin-style metadata, and install pressure.
- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill package with `skills/reverse-flow`, `SKILL.md`, local sandbox and CTF framing, staged workflow language, and scripts.
- `Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` and `Tencent-Hunyuan/Hy3`: workflow/model project evidence that is adjacent to skill routing but not a selected local skill package.

## Hypothesis

Pass 4 should leave an operator-visible completion matrix, not another isolated fixture. Reverse-flow and rnskill should complete skill-route discovery first in bounded local lanes, while Shepherd, Hy3, and workflow-usecase rows remain deferred to `agent_harness_eval_required` until local harness criteria exist.

## Local Changes

- Added `skill_route_discovery_current_digest_20260709T001850_pass4_completion_matrix`.
- Added a focused regression asserting skill rows are bounded to documentation, config, test, or code_patch and adjacent rows do not inherit skill-route lanes.
- Documented the pass-4 completion matrix in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because it already matches this run's choice: rollback-backed local validation before activation.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260709T001850
```

Result: passed, 1 passed and 443 deselected.

No external skill install, upstream code execution, external harness execution, provider runtime launch, promotion, push, restart, profile write, or memory write was performed.

