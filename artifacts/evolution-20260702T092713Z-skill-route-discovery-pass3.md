# Skill Route Discovery Pass 3 Evolution

- Source digest: `github-growth-20260702T092714.857659Z`
- Capability slice: `skill-route-discovery`
- Pass: 3 of 4
- Rollback artifact: `artifacts/rollback-20260702T092713Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T092713Z-skill-route-discovery-pass3`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/ksimback/looper`

Focused review confirmed the carried digest shape: zhengxi-views exposes
skill-package files and source-citation/non-advice boundaries, while
Qwen-AgentWorld, Fundamental-Ava, and looper are general-agent or loop projects
that need local harness evaluation before implementation routes. Workflow-only
usecase signals remain documentation-only unless explicit skill-route evidence
appears.

## Hypothesis

The pass-3 controller should expose an operator-visible activation-review lane
for the current digest instead of leaving the 09:27 window to generic fallback
behavior. That lane should keep zhengxi-views bounded to local
skill-route-discovery validation, keep general-agent projects behind
`agent_harness_eval_required`, and explicitly prevent workflow-only trend
signals from becoming runtime workflow adoption.

## Changes

- Added a digest-specific pass-3 activation-review branch for
  `github-growth-20260702T092714.857659Z`.
- Added a fixture and regression covering the current zhengxi/general-agent
  split plus the workflow-usecase boundary.
- Documented the new pass-3 route surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T092714`
  - Result: 1 passed, 169 deselected.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: 170 passed.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest and (20260702T080714 or 20260702T090714 or pass3)"`
  - Result: 9 passed, 206 deselected.
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: 11 passed.

## Review Notes

- No self-model change was made. The existing self-model already favors
  rollback-backed, locally validated behavior changes over additional
  validation-report-only scaffolding, and this run followed that preference.
- No upstream code was installed, imported, executed, or activated.
- Runtime action, provider launch, external harness execution, remote execution,
  profile writes, memory writes, raw evidence URL export, replay command export,
  and upstream body export remain denied by the new lane.
