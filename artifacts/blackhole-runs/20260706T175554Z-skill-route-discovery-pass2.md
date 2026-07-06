# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260706T175555.480042Z`
- Rollback point: `artifacts/rollback/20260706T175554Z-skill-route-discovery-pass2/rollback-point.md`
- Local rollback ref: `refs/rollback/20260706T175554Z-skill-route-discovery-pass2`

## Evidence

The current digest and focused GitHub review showed one explicit skill workflow
candidate and four adjacent general-agent projects:

- `lingbol088-spec/reverse-flow-skill`: public `skills/reverse-flow` package,
  `SKILL.md`, references, scripts, local sandbox/CTF framing, and install/run
  pressure that remains diagnostic.
- `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`,
  `TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`: general
  agent, benchmark, autonomous-agent, or runtime-substrate claims without an
  explicit local skill workflow route hint or local harness evaluation result.

## Hypothesis

The active pass-2 window should be replayable as a bounded local route-priority
queue: explicit `skill_route_discovery` evidence validates first through local
documentation, config, test, or code_patch lanes, while adjacent general-agent
projects remain behind `agent_harness_eval_required` with no direct
implementation lane before local harness evaluation.

## Local Change

- Added `tests/fixtures/skill_route_discovery/current_digest_20260706T175555_pass2_route_priority.json`.
- Added a regression test for `build_skill_route_discovery_validation_route_packet`.
- Added the replay command and route-policy note to `docs/skill-route-discovery.md`.

## Validation

Commands run:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T175555
python -m pytest tests/test_skill_routing.py -q -k "20260706T151555 or 20260706T163555 or 20260706T175555"
python -m pytest tests/test_docs_contracts.py -q
```

Results:

- `1 passed, 345 deselected`
- `2 passed, 344 deselected`
- `11 passed`

## Review Notes

No external skill code was installed, run, activated, or copied. No provider,
external harness, remote execution, profile write, or memory write path was
opened. The self-model was read and left unchanged because this run produced a
concrete route validation improvement and did not reveal a new behavior-shaping
self-description.
