# Skill Route Discovery Pass 2

Source digest: `github-growth-20260707T054834.215350Z`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with `skills/reverse-flow/SKILL.md`, references, scripts, local sandbox framing, install/run examples, and reverse-analysis workflow pressure.
- `Pluviobyte/rnskill`: public multi-skill collection for Codex, Claude Code, and `SKILL.md`-compatible workflows with `skills/`, docs, tools, marketplace metadata, install examples, and multiple skill packages.

## Hypothesis

Mixed Codex-specific and generic skill workflow trend evidence should be visible as a bounded current-digest pass-2 lane before activation. Codex workflow evidence must preserve its `codex_workflow_gate` profile, generic skill collections must preserve `generic_skill_workflow`, and both may map only to documentation, config, test, or code_patch. Adjacent general-agent projects remain behind `agent_harness_eval_required`.

## Changes

- Added `tests/fixtures/skill_route_discovery/current_digest_20260707T054834_pass2_skill_workflow_route_discovery.json`.
- Added `skill_route_discovery_current_digest_pass2_skill_workflow_route_discovery` dispatch and lane construction in `src/blackhole_agent/skill_routing.py`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Documented the current digest route policy in `docs/skill-route-discovery.md`.

Self-model decision: left unchanged. The existing self-model already supports rollback-backed local evolution with explicit uncertainty and did not need a behavior-shaping update for this bounded validation lane.

## Rollback

- Rollback ref: `refs/rollback/20260707T054832Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260707T054832Z-skill-route-discovery-pass2/rollback-point.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T054834`: passed, 1 passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T054834 or 20260706T105129 or 20260705T084958 or repository_lane_probe"`: passed, 4 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 5 passed.

## Review Notes

- The lane exports source hashes, item IDs, route profiles, and route-family metadata only; raw GitHub URLs, raw replay commands, upstream bodies, runtime action, external skill activation, external harness execution, provider launch, and remote execution remain disabled.
- No external skill installation, clone, script execution, provider launch, or restart was performed.
