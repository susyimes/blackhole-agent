# Evolution Run: Skill Route Discovery Pass 4 Current Window

- Source digest: `github-growth-20260703T191923.842600Z`
- Capability window: `skill-route-discovery`, pass 4 of 4
- Rollback artifact: `artifacts/rollback-20260703T191921Z-skill-route-discovery-pass4-current-window.md`
- Self-model decision: left unchanged; the existing preference for rollback-backed, locally validated evolution matched this run.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Agent/Codex skill package with `skills/reverse-flow` layout, local sandbox/CTF reverse-analysis framing, and install/runtime-looking pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill with source-cited workflow and advice-boundary metadata.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent workflow/evaluation project without a skill-route hint.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project without a skill-route hint.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent simulation project without a skill-route hint.

## Local Change

Added a current-digest pass-4 completion handoff for
`github-growth-20260703T191923.842600Z`. The handoff maps reverse-flow-style
skill evidence to the local `test` lane, zhengxi-style skill workflow evidence
to the `documentation` lane, and general-agent projects to
`agent_harness_eval_required` with no direct local lanes before harness
evaluation. The exported controller surface remains body-free and denies
runtime action, external activation, provider launch, external harness
execution, remote execution, raw source URL export, raw replay command export,
and upstream-body export.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T191923`
- `python -m pytest tests/test_skill_routing.py -q -k "20260703T175922 or 20260703T185923 or 20260703T191923"`

Both commands passed.
