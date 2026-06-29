# Skill Route Discovery Pass 1 Local Lanes

Source digest: `github-growth-20260629T195904.271855Z`

Rollback point:
- Branch: `codex/blackhole-evolve/20260629T195936.102069-run-a-bounded-local-skill-route-discovery-evalua`
- HEAD: `5dacad7e1bfca640b489210b794ae9ee0a6d8760`
- Ref: `refs/blackhole/rollback/20260630T000000Z-skill-route-discovery-pass1-local-lanes`
- Artifact: `artifacts/rollback/20260630T000000Z-skill-route-discovery-pass1-local-lanes.md`

Evidence reviewed:
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

Hypothesis:
The active pass-1 skill-route window should expose a replayable local lane keyed
to the current proposal IDs. COMPASS-style skill ecosystem handoff evidence can
enter the bounded test lane, zhengxi-style agent plus skill workflow evidence
can enter the bounded documentation lane, and general-agent projects should stay
adjacent under `agent_harness_eval_required` until a local harness-evaluation
route validates them.

Change set:
- Added a `github-growth-20260629T195904.271855Z` branch to
  `current_digest_pass1_validation_lane`.
- Added a frozen body-free evidence fixture for the current pass.
- Added regression coverage for bounded lanes, downgraded unsupported lane
  stripping, adjacent general-agent routing, and no raw URL or replay-command
  export.
- Documented the pass-1 interpretation in `docs/skill-route-discovery.md`.

Self-model decision:
`docs/self-model.md` was read and left unchanged. Its current preference already
matches this run: prefer rollback-backed, locally validated behavior changes
without broadening runtime authority.

Review notes:
- AutoCVE remains an anchoring review-boundary proposal only; no offensive,
  unauthorized-access, abuse, or privacy-leakage behavior was implemented.
- This pass does not install, execute, activate, restart, launch providers,
  write profiles, write memory, or export upstream bodies.
