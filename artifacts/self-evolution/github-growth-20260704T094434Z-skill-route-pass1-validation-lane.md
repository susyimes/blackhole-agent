# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260704T094434.421996Z`
- Branch: `codex/blackhole-evolve/20260704T094531.187143-add-or-extend-local-tests-for-skill-route-discov`
- Rollback point: `artifacts/rollback/20260704T094432Z-skill-route-discovery-pass1/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260704T094432Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill package with `skills/reverse-flow`, install examples, scripts, and local sandbox / CTF workflow framing.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with skill metadata, source-cited workflow language, eval/script signals, and advice-boundary framing.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent project evidence without a skill workflow route hint in the carried digest.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent project evidence without a skill workflow route hint in the carried digest.

## Hypothesis

The active pass should be operator-visible as a replayable local validation lane: Codex-oriented skill workflow evidence should enter `skill_route_discovery_first`, generic skill workflow evidence should stay in bounded documentation/config/test/code_patch lanes, and general-agent projects should stay behind `agent_harness_eval_required`.

## Change

- Added a digest-specific pass-1 branch for `github-growth-20260704T094434.421996Z`.
- Added a frozen fixture for the active evidence packet.
- Added a focused regression covering:
  - `p1-skill-route-discovery-codex-workflow`
  - `p2-generic-skill-workflow-route-doc`
  - `p5-route-summary-metadata`
  - `p3-agent-harness-eval-fixtures` adjacent rows
- Documented the replay path in `docs/skill-route-discovery.md`.

## Validation

Commands run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T094434
python -m pytest tests/test_skill_routing.py -q
```

Result:

- Focused replay: `1 passed, 258 deselected`
- Full skill-routing suite: `259 passed`
