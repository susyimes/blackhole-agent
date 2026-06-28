# Skill Route Discovery Pass 3 Focused Validation Packet

Source digest: `github-growth-20260628T182729.632246Z`

Rollback point:
`artifacts/rollback/20260628T182729Z-skill-route-discovery-pass3.md`

Hypothesis:
The active pass-3 skill-route-discovery window already has enough raw route
classification coverage. The useful local improvement is an operator-visible
focused validation packet keyed to the current proposal IDs, with acceptance
gates that keep external skill evidence inside bounded local lanes before any
activation or final-pass handoff.

Evidence reviewed:
- `https://github.com/dongshuyan/compass-skills` as skill ecosystem, state
  handoff, local memory, and profile-boundary evidence.
- `https://github.com/lyra81604/zhengxi-views` as source-cited skill workflow
  evidence with citation and advice-boundary pressure.
- `https://github.com/majidmanzarpour/threejs-game-skills` as Three.js game
  frontend skill workflow evidence with scaffold/runtime/provider pressure
  that remains denied until local validation.
- `https://github.com/QwenLM/Qwen-AgentWorld` as adjacent general-agent
  harness/evaluation evidence, not a skill-route implementation lane.

Changes:
- Added `current_digest_pass3_focused_validation_packet` to the skill-route
  lane map.
- Added a current-digest fixture for the active 18:27 proposal set.
- Added a focused regression test that checks bounded lanes, acceptance gates,
  stripped unsupported lanes, and adjacent Qwen-AgentWorld handling.
- Documented the current pass-3 packet and state/game boundary handling in
  `docs/skill-route-discovery.md`.

Safety and activation notes:
- No upstream code was installed, executed, imported, or activated.
- No provider was launched.
- No restart, push, promotion, or remote execution was performed.
- The packet exports selected item IDs, hashes, lane names, route profiles,
  validation gates, and acceptance gates only; raw source URLs, replay command
  bodies, target paths, and upstream bodies remain denied.
- `docs/self-model.md` was read and left unchanged because its current
  preference already matches this rollback-backed, locally validated behavior
  change and does not need to become more behavior-shaping for this run.

Validation:
- `pytest tests/test_skill_routing.py -q -k current_digest_pass3_focused_validation_packet` passed.
- `pytest tests/test_skill_routing.py -q` passed.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.
