# Skill Route Discovery Pass 4 Completion

- Source digest: github-growth-20260702T030714.684585Z
- Rollback artifact: artifacts/rollback-20260702T030810Z-skill-route-discovery-pass4.md
- Local rollback ref: refs/blackhole-rollback/20260702T030810-skill-route-discovery-pass4
- Branch: codex/blackhole-evolve/20260702T030810.167429-create-a-bounded-local-skill-route-discovery-eva

## Evidence Interpretation

- zhengxi-views exposes Agent Skill package shape through `SKILL.md`,
  `skill.yml`, references, scripts, evals, source-citation requirements, and a
  non-investment-advice boundary.
- NVIDIA BioNeMo Agent Toolkit exposes toolkit-style skill catalog shape through
  skill directories, workflow directories, plugin marketplace metadata, and
  `skills.sh.json`.
- Qwen-AgentWorld remains general-agent benchmark/evaluation evidence. It has
  no skill workflow route hint in the frozen digest and stays behind
  `agent_harness_eval_required` before implementation lanes.

Focused external review used only the carried proposal URLs:

- https://github.com/lyra81604/zhengxi-views
- https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit
- https://github.com/QwenLM/Qwen-AgentWorld

## Local Change

The pass-4 current digest completion handoff now treats the active window as a
candidate-specific closure:

- `p1-skill-route-discovery-zhengxi-views` binds only to `zhengxi-views`.
- `p2-skill-route-discovery-bionemo-agent-toolkit` binds only to
  `bionemo-agent-toolkit`.
- `p3-agent-harness-eval-agentworld` carries Qwen-AgentWorld and Fundamental-Ava
  as adjacent general-agent rows without inheriting `skill_route_discovery`.

This prevents generic skill workflow evidence from merging BioNeMo and zhengxi
into one ambiguous pass-4 row. The handoff keeps install, runtime execution,
provider launch, external skill or agent activation, external harness execution,
remote execution, raw URL export, replay-command export, target-path export, and
upstream-body export denied.

## Validation

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/test_skill_routing.py -q -k "20260702T030714 or 20260702T024715 or 20260702T022714"
$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/test_skill_routing.py -q
$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane
```

Results:

- Focused current-window regression: 3 passed.
- Full skill-routing suite: 153 passed.
- Skill-route docs contracts: 2 passed, 9 deselected.
- Related harness-eval lane checks: 3 passed, 211 deselected.

## Self-Model

`docs/self-model.md` was left unchanged. Its current preference for
rollback-backed, locally validated behavior changes matched this pass, and the
file did not need new structure to explain the change.

## Review Notes

- This pass adds no activation, install, provider runtime, external harness, or
  restart path. Supervisor replay remains external.
- The current digest fixture is body-free and stores selected item summaries,
  local lane hints, and path/metadata signal names, not upstream bodies.
