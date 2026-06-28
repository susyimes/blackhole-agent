# Skill Route Discovery Pass 4 Local-Kernel Handoff

Source digest: `github-growth-20260628T172729.584826Z`

Rollback point:
`artifacts/rollback/20260629T000000Z-skill-route-discovery-pass4-local-kernel.md`

Hypothesis:
The pass-4 skill-route-discovery slice already had enough lane and profile
validation machinery. The useful completion change is an operator-visible
local-kernel handoff that compresses the ready completion report into a bounded
supervisor replay packet, while preserving adjacent general-agent projects as
`agent_harness_eval_required`.

Evidence reviewed:
- `https://github.com/dongshuyan/compass-skills` as state/profile handoff skill
  ecosystem evidence.
- `https://github.com/lyra81604/zhengxi-views` as generic or source-cited skill
  workflow evidence.
- `https://github.com/majidmanzarpour/threejs-game-skills` as game/frontend
  workflow evidence with scaffold/runtime pressure that remains denied.
- `https://github.com/QwenLM/Qwen-AgentWorld` as adjacent general-agent or
  benchmark evidence, not a skill-route implementation lane.

Changes:
- Added `skill_route_discovery_local_kernel_handoff` to the final
  `capability_window_completion` packet.
- Added a current-digest pass-4 fixture that keeps Qwen-AgentWorld and Looper
  as adjacent `agent_harness_eval_required` rows while validating
  documentation/config/test skill-route lanes.
- Updated the aggregate local harness fixture count and added a focused handoff
  test.
- Documented the local-kernel handoff contract in
  `docs/skill-route-discovery.md`.

Safety and activation notes:
- No upstream code was installed, executed, imported, or activated.
- No provider was launched.
- No restart, push, promotion, or remote execution was performed.
- The handoff exports hashes, lane names, route profiles, and recovery status
  only; raw source URLs, replay command bodies, target paths, and upstream
  bodies remain denied.
- `docs/self-model.md` was read and left unchanged because it already matched
  the run policy and did not need to become behavior-shaping for this change.

Validation:
- `pytest tests/test_harness_eval.py -q -k "current_digest_pass4_local_kernel_handoff or skill_route_discovery_lane"` passed.
- `pytest tests/test_harness_eval.py tests/test_docs_contracts.py -q -k "current_digest_pass4_local_kernel_handoff or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or skill_route_discovery_doc"` passed.
- `pytest tests/test_harness_eval.py -q` passed.
- `pytest tests/test_docs_contracts.py -q` passed.
