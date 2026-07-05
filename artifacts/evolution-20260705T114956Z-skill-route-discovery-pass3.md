# Skill Route Discovery Pass 3

Source digest: `github-growth-20260705T114958.132774Z`

Rollback point:
`artifacts/rollback/20260705T114956Z-skill-route-discovery-pass3-current-window/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, references, local sandbox/CTF framing, scripts, install examples, and staged reverse-workflow language.
- `QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and `InternScience/Agents-A1` are general-agent trend signals without explicit skill-route hints.
- `Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases` is workflow-topic evidence without an explicit local skill-route candidate.

## Hypothesis

The current pass should produce an operator-visible route-to-validation lane:
reverse-flow enters a bounded local `test` lane, general-agent projects enter
`agent_harness_eval_required`, and workflow-topic evidence without a skill route
is explicitly blocked from inheriting `skill_route_discovery`.

## Changed Surface

- Added a pass-3 digest branch in `src/blackhole_agent/skill_routing.py`.
- Added a frozen digest fixture in `tests/fixtures/skill_route_discovery/`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Updated `docs/skill-route-discovery.md` with the pass-3 operator rule.

## Review Notes

No upstream code was installed, cloned, or executed. Raw source URLs and replay
commands remain excluded from the operator lane output. The self-model was left
unchanged because the improvement is concrete routing behavior rather than a
change in self-description.
