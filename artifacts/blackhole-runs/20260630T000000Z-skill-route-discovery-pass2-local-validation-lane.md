# Skill Route Discovery Pass 2 Local Validation Lane

Source digest: `github-growth-20260629T173904.211836Z`

Rollback point:

- Branch: `codex/blackhole-evolve/20260629T173939.716397-add-or-run-a-bounded-local-skill-route-discovery`
- Artifact: `artifacts/rollback-20260630T000000Z-skill-route-discovery-pass2-local-validation-lane.md`
- Ref: `refs/blackhole-agent/rollback/20260630T000000Z/skill-route-discovery-pass2-local-validation-lane`

Evidence reviewed:

- Primary carried evidence: `https://github.com/dongshuyan/compass-skills`
- Secondary carried evidence: `https://github.com/lyra81604/zhengxi-views`
- Adjacent harness evidence: `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/ksimback/looper`

Change:

- Added a frozen current-digest pass-2 fixture for COMPASS Skills, zhengxi-views, Qwen-AgentWorld, and looper.
- Made `current_digest_pass2_local_validation_lane` source-digest aware for `github-growth-20260629T173904.211836Z`.
- Mapped COMPASS Skills to the local `test` lane for metadata-only state/profile handoff validation.
- Mapped zhengxi-views to the local `documentation` lane for bounded skill workflow route discovery.
- Kept Qwen-AgentWorld and looper as adjacent `agent_harness_eval_required` evidence without inheriting skill-route authority.

Safety and review notes:

- No install, execution, provider launch, profile write, memory write, remote execution, or upstream body export was added.
- AutoCVE remains review-only context because security-adjacent harness evidence could cross the offensive-behavior or unauthorized-access boundary.
- The self-model was read and left unchanged because it already expresses the current run's preference for rollback-backed, locally validated behavior changes over another report-only artifact.
