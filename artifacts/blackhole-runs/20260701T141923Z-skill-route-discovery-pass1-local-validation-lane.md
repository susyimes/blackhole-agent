# Skill Route Discovery Pass 1 Local Validation Lane

- Source digest: `github-growth-20260701T141923.059729Z`
- Capability slice: `skill-route-discovery`
- Rollback artifact: `artifacts/rollback/20260701T141921Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260701T141921Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shaped repository with `SKILL.md`, `skill.yml`, references, scripts, eval material, source-citation behavior, and non-investment-advice boundaries.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent project evidence; local implementation remains gated by `agent_harness_eval_required`.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general agent project evidence; included only in adjacent comparison metadata.
- `https://github.com/LING71671/open-reverselab`: reverse-engineering automation context; kept review-only at the offensive-behavior boundary.

## Local Change

The router now recognizes this digest as an explicit pass-1 current-digest lane.
`zhengxi-views` maps to `p1-skill-route-discovery-zhengxi-views` in the local
test lane. Qwen-AgentWorld maps to `p2-agent-harness-eval-agentworld`.
Fundamental-Ava and open-reverselab map to `p3-agent-harness-comparison-set`,
with open-reverselab recorded as review-only context.

The lane remains body-free: it exports selected item IDs, lane names, proposal
IDs, route profiles, hashes, and denial booleans only.

## Boundaries

- Runtime action: denied.
- External skill or agent activation: denied.
- External harness execution: denied.
- Provider launch: denied.
- Remote execution: denied.
- Raw source URLs, replay commands, target paths, and upstream bodies: omitted.
- Offensive or abuse-enabling reverse-engineering behavior: review-only.

## Validation

Planned local validation:

```powershell
pytest tests/test_harness_eval.py -q -k 20260701T141923
pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "current_digest_20260701T141923 or skill_route_discovery_current_digest_20260701T141923"
```
