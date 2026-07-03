# Skill Route Discovery Pass 2 Operator Lane

Source digest: `github-growth-20260703T054049.979866Z`
Branch: `codex/blackhole-evolve/20260703T054148.683337-add-or-run-a-bounded-skill-route-discovery-valid`
Rollback artifact: `artifacts/rollback/20260703T054048Z-skill-route-discovery-pass2/rollback-point.json`
Rollback ref: `refs/blackhole-rollback/20260703T054048Z-skill-route-discovery-pass2`

## Hypothesis

The current skill-route discovery pass should expose an operator-visible pass-2
lane for the active digest instead of relying on older reverse-flow fixtures.
Reverse-flow-skill should route through `skill_route_discovery_first` before any
Codex workflow handling, zhengxi-views should stay a bounded generic skill
workflow validation candidate, and adjacent general-agent or workflow-usecase
repositories should remain behind `agent_harness_eval_required`.

## Evidence Interpreted

- `https://github.com/lingbol088-spec/reverse-flow-skill`: treated as metadata
  evidence for a Codex/AI Agent skill package layout with local validation
  scripts and workflow-gate language.
- `https://github.com/lyra81604/zhengxi-views`: treated as metadata evidence
  for a source-cited generic skill workflow package.
- `https://github.com/QwenLM/Qwen-AgentWorld`,
  `https://github.com/TianhangZhuzth/Fundamental-Ava`, and
  `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`:
  treated as adjacent general-agent or workflow-usecase evidence without local
  skill-route activation authority.

## Change

- Added a `github-growth-20260703T054049.979866Z` branch to the current digest
  pass-2 local validation lane builder.
- Added a frozen metadata fixture for this digest with reverse-flow, zhengxi,
  Qwen-AgentWorld, Fundamental-Ava, and Seedance workflow-usecase rows.
- Added regression coverage proving the current active proposal IDs map to
  bounded local lanes, no runtime action, no external activation, and an
  operator-visible activation readiness packet.

## Validation

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "20260703T054049"
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "20260703T054049 or 20260703T050050 or 20260703T044050 or 20260703T042050"
```

Results:

- `1 passed, 201 deselected`
- `4 passed, 198 deselected`

## Review Notes

- No upstream code, raw repository body, replay command, provider route, remote
  execution path, or skill activation was added.
- The self-model was read and left unchanged because its current preference for
  rollback-backed, locally validated behavior matches this run.
