# Skill Route Discovery Pass 4

Source digest: `github-growth-20260704T144434.510329Z`
Branch: `codex/blackhole-evolve/20260704T144526.128317-add-or-run-a-bounded-skill-route-discovery-valid`
Rollback ref: `refs/blackhole-rollback/20260704T144526-skill-route-discovery-pass4`
Rollback artifact: `artifacts/rollback/20260704T144526Z-skill-route-discovery-pass4/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public skill-style repository with `SKILL.md`, `skill.yml`, references, scripts, evals, source-cited research workflow, and explicit research/advice boundary.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/agent skill workflow repository with install or runtime pressure that must remain diagnostic only.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model and benchmark project; requires local agent harness evaluation before implementation lanes.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent project; requires local agent harness evaluation before implementation lanes.

## Hypothesis

The final pass should bind the current skill-route window to an operator-visible
`current_digest_pass4_completion_handoff`, not another standalone fixture.
Generic skill workflow and mixed Codex skill workflow signals should map only to
bounded local lanes with `runtime_action: none`, while adjacent general-agent
projects stay behind `agent_harness_eval_required`.

## Changes

- Added `current_digest_20260704T144434_pass4_completion.json` as the frozen current digest fixture.
- Wired `github-growth-20260704T144434.510329Z` into the specialized pass-4 completion handoff path.
- Added a focused regression proving:
  - `zhengxi-views` maps to `p1-skill-route-discovery-zhengxi-views` in a local test lane.
  - `reverse-flow-skill` maps to `p2-codex-skill-workflow-gate`, preserves `skill_route_discovery_first`, and downgrades install/runtime pressure.
  - Qwen-AgentWorld, Fundamental-Ava, and Awesome-Blender-Seedance-Workflow-Usecases remain `agent_harness_eval_required`.
  - The handoff exports no raw GitHub URLs, replay commands, target paths, or upstream bodies.
- Updated `docs/skill-route-discovery.md` with the pass-4 completion contract.

## Validation

- `python -m py_compile src\blackhole_agent\skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k 20260704T144434`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T144434 or 20260704T142434 or 20260704T130435"`: passed, 4 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.

## Review Notes

Self-model was read and left unchanged. It already matches this run's observed
preference: prefer rollback-backed, locally validated behavior improvements over
validation-report-only changes, while keeping runtime activation and privacy
boundaries external.

No push, promotion, restart, provider launch, external harness execution, or
remote execution was performed. Activation remains a supervisor responsibility.
