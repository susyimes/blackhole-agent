# Skill Route Discovery Pass 2 Current Window

- Source digest: `github-growth-20260629T103324.012579Z`
- Rollback artifact: `artifacts/rollback-20260629T103438Z-skill-route-discovery-pass2.md`
- Evidence URLs: `https://github.com/dongshuyan/compass-skills`, `https://github.com/lyra81604/zhengxi-views`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/ksimback/looper`
- Selected proposal path: active pass-2 skill-route-discovery lane with adjacent general-agent harness-eval gating.

Hypothesis: the active pass-2 controller window should be replayable through the local lane map under its current proposal IDs, without requiring an unrelated game/frontend route profile and without granting runtime authority to general-agent repositories.

Implemented local behavior:

- Specialized `current_digest_pass2_local_validation_lane` for `github-growth-20260629T103324.012579Z`.
- Mapped COMPASS-style skill ecosystem evidence to `p1-skill-route-discovery-registry` in the local test lane.
- Mapped zhengxi-views-style generic skill workflow evidence to `p3-skill-route-docs` in the documentation lane.
- Kept Qwen-AgentWorld and looper under `p2-agent-harness-eval-fixtures` as `agent_harness_eval_required` only.
- Adjusted the active pass-2 acceptance contract so this current two-profile window requires `generic_skill_workflow` and `skill_ecosystem_state_handoff`, not unrelated `game_frontend_workflow` evidence.

Validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "103324_pass2 or current_digest_pass2_active_slice_review or 101324_pass1"
```

Result: passed, `3 passed, 101 deselected`.

Review notes:

- No upstream bodies were imported.
- Raw source URLs, raw evidence URLs, replay command bodies, target paths, and upstream bodies remain omitted from the generated lane surfaces.
- No runtime execution, install, provider launch, external harness execution, profile write, memory write, remote execution, push, promotion, restart, or supervisor activation was performed.
- The self-model was read and left unchanged because its current preference already supports bounded, rollback-backed local behavior changes with explicit validation.
