# Skill Route Discovery Pass 1 Reverse-Flow Validation

- Source digest: `github-growth-20260703T193923.799406Z`
- Branch: `codex/blackhole-evolve/20260703T194018.609970-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback artifact: `artifacts/rollback-20260703T193921Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/blackhole-rollback/20260703T193921Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/TaoDevil/reverse-flow-skill`: carried evidence for a reverse-flow skill-style repository with Codex, agent, skill, and workflow terms.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: carried evidence for a reverse-flow skill-style repository with Codex workflow-gate pressure.
- `https://github.com/lyra81604/zhengxi-views`: carried evidence for a generic Agent Skill workflow with source-citation and advice-boundary metadata.
- `https://github.com/Forsy-AI/agent-apprenticeship`: carried evidence for a general agent project without a skill workflow route hint.

## Hypothesis

Pass 1 should convert the current reverse-flow skill evidence into a replayable local validation lane before any adoption:
reverse-flow repositories map to `skill_route_discovery_first` and only bounded local lanes; generic skill workflow evidence
becomes a checklist/documentation probe; general agent project evidence remains `agent_harness_eval_required` until a local
harness baseline exists.

## Changes

- Registered `github-growth-20260703T193923.799406Z` in the pass-1 skill-route lane builder.
- Added a frozen local harness fixture for the active proposal IDs:
  `p1_reverse_flow_skill_discovery`, `p2_generic_skill_workflow_probe`, and `p3_agent_harness_eval_baseline`.
- Added focused harness assertions for reverse-flow grouping, bounded lanes, no runtime action, no external activation,
  and agent-apprenticeship staying in `agent_harness_eval_required`.
- Documented the pass-1 lane in `docs/skill-route-discovery.md`.

## Validation

Passed local validation:

```bash
$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py -q -k 20260703T193923
$env:PYTHONPATH='src'; python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
```

## Review Notes

- Self-model unchanged: its existing preference already supports rollback-backed local validation and narrow safety review.
- No external repository was cloned, installed, trusted, or executed.
- No restart, push, promotion, provider launch, external harness execution, external skill activation, remote execution,
  profile write, or memory write was performed by this kernel.
