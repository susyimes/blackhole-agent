# Skill Route Discovery Pass 1 Local Validation Lane

- Source digest: `github-growth-20260701T194302.427071Z`
- Capability slice: `skill-route-discovery`
- Pass: 1 of 4
- Rollback ref: `refs/blackhole-rollback/20260701T194301Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public repository page shows Agent Skill package files including `SKILL.md`, `skill.yml`, `references`, `evals`, and `scripts`, with source-citation and non-investment-advice boundaries in the repository description/readme.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent project evidence, not a skill workflow route.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent project evidence, not a skill workflow route.
- `https://github.com/ksimback/looper`: loop/workflow tooling evidence, not a skill workflow route.

## Hypothesis

The current routing surface should make the 19:43 digest replayable as a bounded pass-1 lane: zhengxi-views enters local skill-route validation, while Qwen-AgentWorld, Fundamental-Ava, and looper remain adjacent `agent_harness_eval_required` rows before any implementation or runtime follow-up.

## Change

- Added a digest-specific pass-1 lane specialization for `github-growth-20260701T194302.427071Z`.
- Added a frozen fixture with body-free repository metadata for the four carried evidence items.
- Added a focused regression test proving skill/workflow evidence and general-agent evidence stay separated.
- Updated operator documentation for the current pass.

## Validation

Planned focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260701T194302
```

The lane remains non-activating: no runtime action, provider launch, external harness execution, external skill or agent activation, remote execution, profile write, memory write, raw URL export, replay-command export, target-path export, or upstream-body export is granted.
