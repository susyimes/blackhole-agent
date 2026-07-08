# Skill Route Discovery Pass 3: Current Digest Validation Lane

Source digest: `github-growth-20260708T171850.612077Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository with a `skills/` layout, `SKILL.md`, local sandbox/CTF framing, workflow language, install examples, and script examples. Treat install/run/script wording as route pressure only.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent skills collection. Treat as generic skill-workflow evidence, not activation authority.
- `https://github.com/Tencent-Hunyuan/Hy3`: general agent/model/provider project evidence. Keep behind local agent-harness evaluation before follow-up lanes.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate evidence. Keep behind local agent-harness evaluation before follow-up lanes.

## Hypothesis

The active pass-3 skill-route window should expose an operator-visible lane, not another standalone fixture: reverse-flow and rnskill should become bounded local validation rows, while Hy3 and Shepherd remain adjacent `agent_harness_eval_required` rows with no direct pre-eval lanes.

## Changes

- Added the `github-growth-20260708T171850.612077Z` pass-3 specialization to the existing current-digest route-to-validation path.
- Added explicit `route_kind: skill_workflow` and `route_probe_decision: skill_route_discovery` fields to locally projected skill rows.
- Added a frozen current-digest fixture and regression test for the active proposals.
- Documented the new pass-3 operator lane in `docs/skill-route-discovery.md`.

## Rollback

- Rollback artifact: `artifacts/rollback/20260708T171848Z-skill-route-discovery-pass3/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T171848Z-skill-route-discovery-pass3`
- Rollback execution remains explicit and destructive.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T171850
```

Also passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260708T155850 or 20260708T165850"
python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

## Review Notes

- The self-model was read and left unchanged because it already favors rollback-backed, locally validated behavior changes over report-only evolution.
- No install, provider launch, external skill activation, external harness execution, remote execution, promotion, push, or restart path was added.
