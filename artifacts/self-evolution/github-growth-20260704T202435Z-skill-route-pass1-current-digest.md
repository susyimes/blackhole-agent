# Evolution Run: skill-route-discovery pass 1 current digest

## Evidence

- Source digest: `github-growth-20260704T202435.356776Z`.
- `lingbol088-spec/reverse-flow-skill` presents a Codex/AI Agent skill package with `skills/reverse-flow/SKILL.md`, local sandbox and CTF framing, scripts, install examples, and workflow-gate pressure.
- `lyra81604/zhengxi-views` presents an Agent Skill workflow with skill metadata, references, evals, source-cited research language, and an advice boundary.
- `QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava` are adjacent general-agent projects without `skill_route_discovery` route hints in this run's frozen evidence.

## Hypothesis

Pass-1 route discovery should make mixed skill workflow evidence replayable as bounded local lanes before activation. Codex workflow profiles must prove `skill_route_discovery_first`; adjacent general-agent evidence must be routed to `agent_harness_eval_required` and must not inherit skill-route lanes.

## Change

- Added `tests/fixtures/skill_route_discovery/current_digest_20260704T202435_pass1_skill_route_validation_lane.json`.
- Added a focused regression in `tests/test_skill_routing.py` for the current digest's skill-route and adjacent agent-harness split.
- Left `docs/self-model.md` unchanged because it already matches this run's validated-local-evolution preference and did not add a useful behavior constraint.

## Rollback

- Rollback artifact: `artifacts/rollback/20260704T202533Z-skill-route-discovery-pass1-current-digest/rollback-point.md`.
- Rollback ref: `refs/rollback/20260704T202533Z-skill-route-discovery-pass1-current-digest`.

## Validation

- First run of `python -m pytest tests/test_skill_routing.py -q -k 20260704T202435` failed because the fixture intentionally lacks game/state-handoff evidence and therefore blocks the broader fixed current-digest pass-1 lane.
- The regression was adjusted to assert the route classifier's bounded local lane matrix plus adjacent agent-harness rows directly.
- `python -m pytest tests/test_skill_routing.py -q -k 20260704T202435`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T202435 or 20260704T091310 or 20260704T011308"`: passed, 3 tests.

## Review Notes

- This change does not install, import, execute, or activate upstream skill or agent code.
- Unsupported upstream pressure such as `install`, `runtime_execution`, and `provider_runtime` is expected to be downgraded or omitted from exported route lanes.
