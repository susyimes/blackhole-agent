# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260704T071309.705655Z`
- Capability theme: `skill-route-discovery`
- Pass: 2 of 4
- Rollback artifact: `artifacts/rollback/20260704T071307Z-skill-route-discovery-pass2-current-window/rollback-point.md`
- Rollback ref: `refs/blackhole-rollback/20260704T071307Z-skill-route-discovery-pass2-current-window`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow repository with `skills/reverse-flow/SKILL.md`, install examples, scripts, local sandbox/CTF framing, and runtime pressure that must remain diagnostic only.
- `lyra81604/zhengxi-views`: public Agent Skill workflow evidence with source-citation and advice-boundary metadata.
- `QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava`: general agent project evidence without a direct skill workflow route hint.

## Hypothesis

The current pass-2 digest should replay through a digest-specific local validation lane instead of relying on older pass-2 windows. Codex workflow skill evidence should remain `skill_route_discovery_first`; generic skill workflow evidence should select documentation; general agent projects should stay behind `agent_harness_eval_required` before any direct code_patch or runtime route.

## Local Change

- Added the current digest fixture `tests/fixtures/skill_route_discovery/current_digest_20260704T071309_pass2_validation_lane.json`.
- Wired `github-growth-20260704T071309.705655Z` into the existing pass-2 skill-route builder with current proposal IDs.
- Added a focused regression test for the current pass-2 lane, operator replay surface, and supervisor handoff denial fields.
- Documented the current pass-2 route in `docs/skill-route-discovery.md`.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T071309
python -m pytest tests/test_skill_routing.py -q -k "20260704T071309 or 20260704T065309 or 20260704T055309"
python -m pytest tests/test_skill_routing.py -q
```

No activation, restart, push, provider launch, external harness execution, or remote execution is performed by this kernel run.
