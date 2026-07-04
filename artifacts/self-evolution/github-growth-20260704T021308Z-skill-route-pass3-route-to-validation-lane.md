# Skill Route Discovery Pass 3 Route-To-Validation Lane

Source digest: github-growth-20260704T021308.794520Z
Theme: skill-route-discovery
Pass: 3 of 4

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill` provided Codex/Agent Skill workflow evidence and was kept behind `skill_route_discovery_first`.
- `https://github.com/lyra81604/zhengxi-views` exposed `SKILL.md`, `skill.yml`, references, scripts, evals, and source-citation/advice-boundary language suitable only for bounded local lanes.
- `https://github.com/QwenLM/Qwen-AgentWorld` is broader general-agent evidence without skill workflow route hints, so it remains adjacent `agent_harness_eval_required` evidence before any implementation lane.

## Change

Added a local harness replay fixture for `github-growth-20260704T015308.851001Z` that validates the current pass-3 route-to-validation lane:

- Skill-like evidence maps only to documentation, config, test, and code_patch lanes.
- Mixed Codex/skill evidence records `skill_route_discovery_first` and no runtime action.
- General agent projects without skill workflow signals stay in `agent_harness_eval_required` and do not receive direct runtime or code patch authority.

## Rollback

Rollback ref: `refs/rollback/blackhole-evolve/20260704T021307Z`
Rollback artifact: `artifacts/rollback/20260704T021307Z-skill-route-discovery-pass3/rollback-point.md`

## Validation

Planned local validation:

```powershell
pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures or 20260704T015308"
pytest tests/test_skill_routing.py -q -k "20260704T015308 or pass3"
```

Runtime activation, external harness execution, provider launch, and remote execution remain denied by the replayed lane.
