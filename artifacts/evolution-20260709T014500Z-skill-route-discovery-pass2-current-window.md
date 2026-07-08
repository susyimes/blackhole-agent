# Skill Route Discovery Pass 2 Current Window

- Source digest: `github-growth-20260708T205851.045193Z`
- Capability theme: `skill-route-discovery`
- Capability pass: 2 of 4
- Rollback ref: `refs/rollback/blackhole-agent/20260709T014500Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260709T014500Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository metadata shows a Codex / AI Agent skill package, `skills/reverse-flow`, `SKILL.md`, local sandbox / CTF framing, staged workflow language, and script/install examples.
- `https://github.com/Pluviobyte/rnskill`: public repository metadata shows an AI Agent Skills collection for Codex, Claude Code, and other `SKILL.md`-compatible workflows, with `skills`, docs, tools, plugin-style metadata, and install pressure.

## Hypothesis

The current reverse-flow/rnskill trend evidence should advance from discovery into an operator-visible pass-2 validation lane. The lane should preserve `skill_route_discovery_first`, map skill evidence only to documentation, config, test, or code_patch lanes, and keep Shepherd/Hy3 behind local agent-harness evaluation before any implementation follow-up.

## Local Change

- Added `skill_route_discovery_current_digest_20260708T205851_pass2_validation_lane`.
- Added a frozen body-free fixture for the current digest.
- Added focused routing and docs-contract tests.
- Updated `docs/skill-route-discovery.md` with the current pass-2 interpretation path.
- Left `docs/self-model.md` unchanged because it already states the relevant preference for rollback-backed local validation over validation-report-only work.

## Validation

Run:

```powershell
python -m pytest tests/test_skill_routing.py tests/test_docs_contracts.py -q -k "20260708T205851 or doc_records_20260708T205851"
```

Expected: the new lane is ready, exposes only bounded local lanes, keeps adjacent agent projects behind `agent_harness_eval_required`, and exports no raw source URLs or replay commands in the packet.
