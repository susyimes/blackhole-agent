# Skill Route Discovery Pass 4 Final Lane

- Source digest: `github-growth-20260701T180302.906845Z`
- Capability theme: `skill-route-discovery`
- Pass: 4 of 4
- Rollback artifact: `artifacts/rollback-20260701T180431Z-skill-route-discovery-pass4-final.md`
- Rollback ref: `refs/rollback/skill-route-discovery-pass4-final-20260701T180431Z`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/ksimback/looper`

The focused review found that `zhengxi-views` exposes Agent Skill route evidence
through repository metadata such as `SKILL.md`, `skill.yml`, references, evals,
scripts, source-citation boundaries, and non-investment-advice language.
Qwen-AgentWorld, Fundamental-Ava, and looper are useful public agent-project
signals, but they lack a local skill-route hint and a completed local harness
evaluation in this run.

## Local Change

Added a source-digest-specific pass-4 final closure lane for
`github-growth-20260701T180302.906845Z`. The lane maps the skill-route evidence
only to bounded test and documentation lanes, keeps runtime action denied, and
keeps adjacent general-agent projects under `agent_harness_eval_required` until
a local harness result selects a follow-up lane.

## Validation

Commands run:

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260701T180302
python -m pytest tests/test_skill_routing.py -q
```

Results:

- Focused current-digest regression: `1 passed, 135 deselected`
- Full skill-routing suite: `136 passed`

Self-model decision: unchanged. The current self-model already describes the
preference used here: apply rollback-backed, locally validated behavior changes
while keeping offensive behavior, abuse, unauthorized access, and privacy
leakage outside automatic activation.
