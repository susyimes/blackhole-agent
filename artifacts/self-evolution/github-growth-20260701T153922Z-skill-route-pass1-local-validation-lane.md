# Skill Route Discovery Pass 1 Local Validation Lane

Source digest: `github-growth-20260701T153922.962740Z`

Hypothesis: the current trend window should route public Agent Skill evidence into bounded local validation lanes while keeping adjacent general-agent projects in `agent_harness_eval_required` until a local harness result exists.

Evidence reviewed:

- `https://github.com/lyra81604/zhengxi-views`: repository exposes an Agent Skill package shape, including `SKILL.md`, `skill.yml`, `references/`, `scripts/`, source-citation constraints, and non-advice boundaries.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent project with environment simulation and benchmark claims, not a local skill package.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent project without local skill-route evidence.
- `https://github.com/ksimback/looper`: review-gated agent-loop design project, useful as adjacent harness-eval evidence but not direct skill-route evidence.

Change summary:

- Added `github-growth-20260701T153922.962740Z` handling to the pass-1 `skill_route_discovery` controller lane.
- Added a frozen local harness fixture for the current digest.
- Added harness assertions that `zhengxi-views` maps only to documentation, config, test, or code patch lanes; Qwen-AgentWorld, Fundamental-Ava, and looper remain `agent_harness_eval_required`; and `p3_agent_automation_bug_eval` remains review-only at the offensive-behavior boundary.

Rollback:

- Rollback artifact: `artifacts/self-evolution/github-growth-20260701T153922Z-skill-route-pass1-rollback.md`
- Rollback ref: `refs/blackhole/rollback/github-growth-20260701T153922Z-skill-route-pass1`

Validation:

```powershell
pytest tests/test_harness_eval.py -q -k 20260701T153922
pytest tests/test_harness_eval.py -q -k "20260701T141923 or 20260701T153922"
pytest tests/test_harness_eval.py -q -k "pass1_local_validation_lane"
pytest tests/test_skill_routing.py -q -k "current_digest_pass1_validation_lane or 20260701T131922 or 20260701T133922"
pytest tests/test_harness_eval.py tests/test_skill_routing.py -q
```

All commands passed. The full affected-file run reported `337 passed`.

Review notes:

- No runtime, provider, remote execution, profile write, memory write, external harness execution, or external skill activation path was added.
- `p3_agent_automation_bug_eval` remains review-only; no offensive, exploit, malware, phishing, exfiltration, unauthorized-access, or reverse-engineering behavior was implemented.
- The self-model was read and left unchanged because its current preference already matches this run's bounded, rollback-backed local validation behavior.
