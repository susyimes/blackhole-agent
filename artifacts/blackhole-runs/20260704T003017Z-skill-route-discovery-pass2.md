# Skill Route Discovery Pass 2 Run Note

Source digest: `github-growth-20260704T002924.779596Z`
Rollback ref: `refs/blackhole-agent/rollback/20260704T003017Z`

Evidence reviewed:

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes `SKILL.md`, `skill.yml`, references, evals, scripts, source-citation language, and an advice disclaimer. Local route: bounded `skill_route_discovery` test lane.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository is Codex/Agent skill-workflow themed and security-adjacent. Local route: `skill_route_discovery_first` test lane only; no install, runtime execution, provider launch, or external skill activation.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public repository is a general agent benchmark/world-model project, not a skill workflow. Local route: adjacent `agent_harness_eval_required`.

Change summary:

- Added a frozen current pass-2 fixture for the active capability window.
- Registered the active source digest in the current digest pass-2 lane builder.
- Added a focused regression test proving skill evidence stays in bounded local lanes and general agent/workflow evidence remains blocked behind agent-harness evaluation.

Self-model decision:

Left unchanged. The current self-model already prefers locally validated, rollback-backed behavior changes over report-only scaffolding, and this run implements that path directly.
