# Blackhole Run: skill-route-discovery pass 3

- Source digest: `github-growth-20260707T102834.622372Z`
- Branch: `codex/blackhole-evolve/20260707T102911.734803-create-a-local-skill-route-discovery-validation-`
- Rollback artifact: `artifacts/blackhole-runs/20260707T102832Z/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260707T102832Z-skill-route-discovery-pass3`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, scripts, and install/run examples.
- `https://github.com/Pluviobyte/rnskill`: generic AI Agent Skills collection with SKILL.md-compatible workflows, `skills`, docs, tools, marketplace metadata, and install examples.
- `https://github.com/InternScience/Agents-A1`: general long-horizon agent/model/evaluation project.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous collaborative agent project.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate with reversible trace and replay claims.

## Hypothesis

The current pass-3 mixed window should expose a supervisor-visible validation lane for the exact source digest. Skill workflow rows should stay in bounded local lanes, while adjacent general-agent projects remain gated behind `agent_harness_eval_required` until local harness evidence exists.

## Change

- Added `skill_route_discovery_current_digest_20260707T102834_pass3_validation_lane`.
- Added a frozen current-digest fixture and regression coverage.
- Documented the operator-visible lane and replay command.
- Left `docs/self-model.md` unchanged because the existing self-model already supports rollback-backed local behavior changes and did not need new behavior-shaping content for this run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T102834`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T090834 or 20260707T102834"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route`: passed, 6 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 374 tests.

## Review Notes

- The lane is metadata-only and body-free. It denies raw URL/body export, replay-command export, install/runtime/provider/external-harness execution, remote execution, profile writes, memory writes, and external skill or agent activation.
- General-agent projects remain adjacent harness-eval candidates and do not inherit skill-route lanes.
