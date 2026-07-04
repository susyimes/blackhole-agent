# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260704T015308.851001Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260704T015616Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260704T015616Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package with `skills/reverse-flow/SKILL.md`, scripts, and local sandbox/CTF workflow language. Reusable lesson: treat as `codex_workflow_gate` evidence, not as an install or execution instruction.
- `https://github.com/lyra81604/zhengxi-views`: Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation behavior, and a non-investment-advice boundary. Reusable lesson: generic/source-cited Skill repositories map first to bounded local documentation/config/test/code_patch lanes.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent model/benchmark repository. Reusable lesson: keep general-agent projects behind `agent_harness_eval_required` before local implementation lanes open.

## Change

Added a digest-specific pass-2 validation lane for `github-growth-20260704T015308.851001Z`.

- `p1-skill-route-discovery-codex-workflow`: selects the local `test` lane and requires `skill_route_discovery_first`.
- `p2-generic-skill-workflow-discovery`: selects the local `documentation` lane for generic/source-cited Skill workflow evidence.
- `p3-agent-harness-eval-trending-agent-projects`: keeps Qwen-AgentWorld and Fundamental-Ava as adjacent harness-eval backlog rows.
- `p4-workflow-usecase-evaluation`: keeps workflow-only usecase evidence out of direct skill-route lanes.

The lane exports hashes, item IDs, route profiles, lane names, and denial booleans only. It does not export raw source URLs, replay commands, upstream bodies, or target paths.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T015308
```

## Review Notes

- Self-model left unchanged; it already matches this run's rollback-backed, validation-first local evolution policy.
- External activation, provider launch, external harness execution, remote execution, profile writes, memory writes, and runtime action remain denied.
