# Skill Route Discovery Pass 2

Source digest: `github-growth-20260702T170629.644914Z`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: public repository shape includes `SKILL.md`, `skill.yml`, `evals/`, `references/`, and `scripts/`, so it is valid skill-route discovery evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/ksimback/looper`: public repository descriptions indicate general agent, benchmark, autonomous-agent, or loop workflow projects without the same skill-package route signal in this pass.

## Hypothesis

Pass 2 should not stop at another route fixture. It should expose a replayable preactivation checklist that tells an operator which local checks are required before any bounded skill-route lane or adjacent agent-harness lane can be activated.

## Changes

- Registered the active digest `github-growth-20260702T170629.644914Z` in the pass-2 skill-route lane mapper.
- Added `preactivation_checklist` to the pass-2 lane output with body-free item-ID-only evidence, allowed skill-route lanes, general-agent harness requirements, and denied runtime/external activation flags.
- Added a frozen current-window RepositoryTrend matrix covering zhengxi-views plus Qwen-AgentWorld, Fundamental-Ava, looper, and workflow-only usecase evidence.
- Added focused direct route-map and harness-surface regression tests.

## Self-Model

Read `docs/self-model.md` and left it unchanged. The current file already says useful growth should prefer rollback-backed, locally validated behavior changes over report-only scaffolding, which matches this pass.

## Rollback

Rollback ref: `refs/blackhole/rollback/20260703T010625Z-skill-route-discovery-pass2`

Rollback artifact: `artifacts/rollback-20260703T010625Z-skill-route-discovery-pass2.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260702T170629_pass2"`: passed.
- `python -m py_compile src/blackhole_agent/skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260702T170629_pass2 or 20260702T154626_pass2"`: passed.

Review note: an exact-node harness regression in `tests/test_harness_eval.py` was tried and removed because the file-level harness collection/evaluation exceeded five minutes in this checkout. The behavior change is in `build_skill_route_discovery_proposal_lane_map`, and the direct route-map regression validates the emitted operator checklist without adding a slow validation trap.
