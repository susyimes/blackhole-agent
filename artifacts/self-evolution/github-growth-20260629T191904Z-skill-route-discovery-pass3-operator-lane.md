# Skill Route Discovery Pass 3 Operator Lane

Source digest: `github-growth-20260629T191904.276263Z`

Hypothesis: the active pass-3 skill-route slice should expose the current
proposal IDs through the existing operator lane instead of relying on the older
`175904` proposal aliases. COMPASS and zhengxi-views should remain bounded
`skill_route_discovery` candidates, while Qwen-AgentWorld and looper should
stay adjacent `agent_harness_eval_required` rows before any implementation
route.

Evidence reviewed:

- `https://github.com/dongshuyan/compass-skills`: public skill ecosystem and
  handoff/profile signal.
- `https://github.com/lyra81604/zhengxi-views`: public generic skill workflow
  signal.
- `https://github.com/QwenLM/Qwen-AgentWorld`: adjacent general-agent
  evaluation signal.
- `https://github.com/ksimback/looper`: adjacent general-agent loop signal.

Changes:

- Added rollback artifact `artifacts/self-evolution/github-growth-20260629T191904Z-rollback.md`
  and rollback ref `refs/rollback/blackhole-agent/20260629T191904Z`.
- Added frozen fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260629T191904_pass3_operator_lane.json`.
- Extended `current_source_digest_pass3_operator_lane` to recognize
  `github-growth-20260629T191904.276263Z` and current proposal IDs.
- Added regression coverage that skill-route rows preserve
  `skill_route_discovery`, export only documentation/config/test/code_patch
  lanes, and keep Qwen-AgentWorld/looper in `agent_harness_eval_required`.
- Documented the pass-3 interpretation in `docs/skill-route-discovery.md`.

Self-model decision:

- `docs/self-model.md` was read and left unchanged. Its current preference
  already fits this run: direct, rollback-backed local behavior change with
  focused validation and a narrow safety boundary.

Review notes:

- AutoCVE remains review-only; no offensive or vulnerability-execution route
  was added.
- Unsupported upstream pressure such as `install`, `provider_runtime`, and
  `runtime_execution` is present only in frozen input evidence and is not
  exported by the operator lane.
