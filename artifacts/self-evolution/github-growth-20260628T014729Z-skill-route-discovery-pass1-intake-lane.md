# Self-Evolution Run: Skill Route Discovery Pass 1 Intake Lane

- Source digest: `github-growth-20260628T014729.582985Z`
- Branch: `codex/blackhole-evolve/20260628T014814.122782-document-a-bounded-skill-route-discovery-intake-`
- Rollback artifact: `artifacts/rollback/20260628T014814Z-skill-route-discovery-pass1-intake-lane.md`
- Rollback ref: `refs/rollback/20260628T014814Z-skill-route-discovery-pass1-intake-lane`

## Hypothesis

The active skill-route-discovery pass should expose an operator-visible intake
lane for the current proposal family before activation. Skill-oriented evidence
from COMPASS Skills, zhengxi-views, and Three.js Game Skills can map to bounded
documentation, config, test, or code_patch lanes with local validation required.
Qwen-AgentWorld-style general-agent evidence should remain adjacent
`agent_harness_eval_required` and should not inherit direct skill-route,
runtime, or code_patch authority.

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem with
  skills directory and state/profile handoff pressure.
- `https://github.com/lyra81604/zhengxi-views`: source-cited agent skill
  evidence with citation and advice-boundary pressure.
- `https://github.com/majidmanzarpour/threejs-game-skills`: Three.js browser
  game skill package with QA/frontend validation pressure.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent evaluation/project
  evidence without skill workflow route signals.

## Change Summary

- Added `current_window_pass1_discovery_intake_lane` to the skill-route proposal
  lane map.
- Added a frozen current-window evidence fixture for the five active proposal
  IDs.
- Added a focused regression asserting bounded lanes, selected local lanes,
  local validation requirements, raw URL/body suppression, and Qwen-AgentWorld
  adjacent eval routing.
- Documented the new pass-1 intake lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_window_pass1_discovery_intake_lane`
  - Result: passed, `1 passed, 58 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `59 passed`
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, `11 passed`

## Review Notes

- No self-model edit was made. The existing self-model already prefers
  rollback-backed, locally validated behavior changes over report-only work,
  which matches this run.
- No activation, install, provider launch, external harness execution, profile
  write, memory write, push, promotion, or restart was performed.
- The new lane is a supervisor replay and intake surface only; activation
  remains external to this kernel run.
