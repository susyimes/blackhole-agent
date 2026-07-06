# Skill Route Discovery Pass 2 Route Priority

- Source digest: `github-growth-20260706T163555.630406Z`
- Theme: `skill-route-discovery`
- Rollback point: `artifacts/rollback/20260706T163729Z-skill-route-discovery-pass2/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T163729Z-skill-route-discovery-pass2`

## Evidence Review

`lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill package shape:
`skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and
CTF/crackme framing, install examples, and run examples. That is useful route
evidence, but its reverse-engineering workflow and execution examples should not
be directly installed or run by this agent.

`InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
`TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd` are broader
general-agent project signals. This pass treats them as harness-evaluation
pressure only, not implementation authority.

## Hypothesis

A current-digest route-priority fixture gives the supervisor an operator-visible
validation queue: explicit skill-route evidence validates first through bounded
local lanes, while adjacent general-agent projects stay behind
`agent_harness_eval_required`.

## Local Change

- Added `tests/fixtures/skill_route_discovery/current_digest_20260706T163555_pass2_route_priority.json`.
- Added a regression in `tests/test_skill_routing.py` that verifies:
  - reverse-flow maps only to documentation, config, test, or code_patch;
  - selected evidence references remain item IDs;
  - general-agent projects expose no direct implementation lane before harness evaluation;
  - runtime action, external activation, provider launch, external harness execution, remote execution, and raw URL export stay disabled.
- Updated `docs/skill-route-discovery.md` with the current pass-2 replay path.
- Left `docs/self-model.md` unchanged because it already permits rollback-backed, locally validated evolution and does not grant permissions.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T163555
# 1 passed, 342 deselected

python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass2_prioritizes_route_hints or 20260706T163555"
# 2 passed, 341 deselected

python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
# 2 passed, 9 deselected
```
