# Blackhole Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260702T084714.820443Z`
- Rollback artifact: `artifacts/rollback-20260702T084812Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/blackhole-rollback/20260702T084812Z-skill-route-discovery-pass1`

## Evidence Review

Focused review used only the carried proposal URLs. `lyra81604/zhengxi-views`
exposes a public `SKILL.md`, `skill.yml`, references, scripts, evals, and a
source-cited research workflow with an explicit non-investment-advice boundary.
`QwenLM/Qwen-AgentWorld`, `TianhangZhuzth/Fundamental-Ava`, and
`ksimback/looper` are broader public agent, benchmark, simulation, or loop
projects. They are useful for an agent-harness evaluation lane, but not for
direct skill-route activation.

## Hypothesis

The current pass should expose an operator-visible pass-1 validation lane keyed
to `github-growth-20260702T084714.820443Z`: zhengxi stays in bounded
`skill_route_discovery` lanes, while Qwen-AgentWorld, Fundamental-Ava, and
looper remain adjacent `agent_harness_eval_required` rows until a local harness
evaluation result exists.

## Self-Model Decision

`docs/self-model.md` was read. It already says useful behavior changes should be
preferred when rollback-backed and locally validated. No edit was made because a
new self-model paragraph would not change behavior for this run.

## Material Actions

- Created rollback ref and rollback artifact.
- Added a frozen current-digest fixture.
- Added a digest-specific pass-1 route specification.
- Added a focused route-lane regression test.
- Updated the skill-route discovery documentation with the current digest lane.

## Validation

- `pytest tests/test_skill_routing.py -q -k "20260702T084714 or 20260702T072714"`: passed, 2 passed.
- `pytest tests/test_skill_routing.py -q -k "current_digest_pass1_validation_lane or 20260702T084714"`: passed, 2 passed.
- `ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
- `pytest tests/test_skill_routing.py -q`: passed, 168 passed.
