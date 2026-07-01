# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260701T223748.552762Z`
- Branch: `codex/blackhole-evolve/20260701T223841.788799-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/blackhole-agent/20260701T223747Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260701T223747Z-skill-route-discovery-pass1.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/ksimback/looper`

The focused review kept zhengxi-views as the only skill-route candidate because
its public repository metadata exposes Agent Skill structure (`SKILL.md`,
`skill.yml`, `references/`, `scripts/`, and `evals/`) plus source-citation and
non-investment-advice boundaries. Qwen-AgentWorld, Fundamental-Ava, and looper
remained general-agent or agent-loop evidence without skill workflow route hints.

## Hypothesis

The current pass should have an operator-visible lane that routes agent plus
skill workflow evidence to `skill_route_discovery` while forcing general-agent
trend items without skill workflow signals through `agent_harness_eval_required`
before any documentation, test, code_patch, runtime, provider, or external
harness follow-up is selected.

## Local Change

- Added a digest-specific pass-1 lane for `github-growth-20260701T223748.552762Z`.
- Added a frozen local fixture for zhengxi-views, Qwen-AgentWorld, Fundamental-Ava, and looper.
- Added regression coverage for bounded local lanes, denied runtime/provider/external execution, and body-free lane export.
- Documented the route boundary in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260701T223748 or 20260701T194302 or 20260701T182302"`: 3 passed.
- `python -m pytest tests/test_skill_routing.py -q`: 144 passed.

## Review Notes

- No upstream code, sample, harness, provider runtime, or external skill was executed.
- Self-model was read and left unchanged because the existing preference already matched this run's evidence-backed local evolution rule.
