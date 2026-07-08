# Evolution Run: Skill Route Discovery Pass 1 Hy3 Preflight

- Source digest: `github-growth-20260708T000200.125943Z`
- Branch: `codex/blackhole-evolve/20260708T000259.560129-document-the-skill-route-discovery-decision-path`
- Rollback ref: `refs/blackhole/rollback/20260708T000158Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260708T000158Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Review

Reviewed only the proposal evidence URLs for this wake. `Pluviobyte/rnskill`
shows a generic `SKILL.md` skill collection shape with skill directories,
docs, tools, plugin metadata, and install pressure. `lingbol088-spec/reverse-flow-skill`
shows a Codex/AI Agent workflow skill shape with local sandbox framing and
diagnostic scripts, so it remains a bounded skill-route test row. `shepherd-agents/shepherd`
is a reversible runtime substrate and stays adjacent agent-harness evidence.
Hy3 issues request API quickstart/examples and an MCP server with environment
variable API-key handling, so they justify only disabled local provider/MCP
preflight metadata before any integration path.

## Change

Added a pass-1 fixture and controller surface for
`github-growth-20260708T000200.125943Z`. The new lane keeps skill evidence in
documentation/test lanes, keeps Shepherd behind `agent_harness_eval_required`,
and records `skill_route_discovery_hy3_provider_mcp_preflight_lane` for
configuration detection, endpoint shape validation, required env-key presence,
MCP stdio metadata, and disabled-by-default checks.

Denied actions remain explicit: provider runtime launch, network calls,
external harness execution, remote execution, API-key hardcoding, raw evidence
URL export, raw provider config export, and raw secret export.

## Self-Model

`docs/self-model.md` was left unchanged. It already expresses the behavior used
in this run: prefer rollback-backed, locally validated repository improvements
over ornamental validation reports while keeping privacy leakage and unsafe
external activation outside the autonomous lane.

## Validation

Focused validation passed:

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260708T000200
python -m pytest tests/test_docs_contracts.py -q -k 20260708T000200
```

Results: both commands passed.
