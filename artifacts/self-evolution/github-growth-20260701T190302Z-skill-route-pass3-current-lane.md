# Skill Route Discovery Pass 3 Current Lane

- Source digest: `github-growth-20260701T190302.389615Z`
- Rollback artifact: `artifacts/rollback/20260702T000000Z-skill-route-discovery-pass3-current.md`
- Rollback ref: `refs/blackhole/rollback/20260702T000000Z-skill-route-discovery-pass3-current`
- External evidence reviewed: zhengxi-views, Qwen-AgentWorld, Fundamental-Ava, looper GitHub repository pages.

## Hypothesis

The current pass-3 controller surface should name the active digest directly:
zhengxi-views can enter bounded skill-route test and documentation lanes, while
general agent projects without skill workflow route hints remain in
`agent_harness_eval_required` until local harness evaluation passes.

## Local Change

- Added a `github-growth-20260701T190302.389615Z` pass-3 lane in
  `src/blackhole_agent/skill_routing.py`.
- Added direct and harness-eval replay fixtures for the current digest.
- Updated route documentation with the current lane distinction.
- Left `docs/self-model.md` unchanged because it already describes the
  run policy used here: prefer rollback-backed, locally validated behavior
  changes and keep only offensive behavior or privacy leakage review-only.

## Replay

Run:

```powershell
pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260701T190302
```

The expected route keeps `runtime_action: none`, denies external activation,
and omits raw source URLs, raw evidence URLs, replay commands, target paths,
and upstream bodies.
