# Evolution Run: skill-route-discovery pass 3 current digest

Source digest: `github-growth-20260703T115316.886295Z`

Rollback ref: `refs/blackhole-rollback/20260703T115315Z-pass3-skill-route-discovery`

Rollback artifact: `artifacts/rollback-20260703T115315Z-pass3-skill-route-discovery.md`

## Hypothesis

Current Codex-oriented skill workflow evidence should be replayable through the pass-3 route-to-validation lane with an explicit `skill_route_discovery_first` marker before any secondary workflow interpretation. Generic skill workflow evidence remains bounded to local validation lanes, and adjacent general-agent projects remain behind `agent_harness_eval_required`.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`

## Local Changes

- `src/blackhole_agent/skill_routing.py`: added current digest pass-3 proposal IDs and exposed `route_probe_decisions` plus `skill_route_discovery_first` on pass-3 rows.
- `tests/fixtures/skill_route_discovery/current_digest_20260703T115316_pass3_route_to_validation.json`: added a frozen four-item current digest fixture.
- `tests/test_skill_routing.py`: added focused pass-3 assertions for Codex workflow routing and adjacent general-agent harness gating.
- `docs/skill-route-discovery.md`: documented the current digest replay rule.

## Validation

Passed:

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T115316`
- `python -m pytest tests/test_skill_routing.py -q -k "20260703T100051 or 20260703T115316"`
- `python -m pytest tests/test_skill_routing.py -q`

## Review Notes

No external skill, provider, harness, remote execution, install, or raw upstream body path was added. The generic skill workflow documentation proposal remains reviewable; the local change only records bounded validation behavior.
