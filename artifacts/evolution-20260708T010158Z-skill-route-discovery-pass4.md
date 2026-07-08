# Evolution Run: skill-route-discovery pass 4 completion

- Source digest: `github-growth-20260708T010200.023332Z`
- Branch: `codex/blackhole-evolve/20260708T010230.024102-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T010158Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260708T010158Z-skill-route-discovery-pass4.md`
- Self-model changed: false

## Evidence

The active window carried reverse-flow skill, rnskill, Shepherd, and Hy3
provider/MCP issue evidence. The reusable lesson is that skill and provider
route evidence should become bounded local lanes before activation: Codex
skill workflow evidence enters `skill_route_discovery` first, generic
`SKILL.md` collections remain documentation/test/config/code_patch candidates,
general-agent runtime projects require `agent_harness_eval_required`, and
provider/MCP pressure remains disabled preflight metadata until local checks
exist.

## Hypothesis

Adding a pass-4 completion handoff for this digest gives operators one
replayable local closure packet instead of leaving the active slice as a
pass-3 handoff plus separate Hy3 preflight note. The packet should expose only
bounded local lanes, keep Shepherd out of direct implementation, and keep Hy3
provider runtime, network calls, external harness execution, remote execution,
and secret export denied.

## Changes

- Extended `skill_route_discovery_current_pass4_completion_handoff` for
  `github-growth-20260708T010200.023332Z`.
- Added `skill_route_discovery_pass4_provider_mcp_preflight_followup` for Hy3
  API/MCP issue rows with documentation, config, and test as the only follow-up
  lanes.
- Added `current_digest_20260708T010200_pass4_completion.json` as the frozen
  local fixture.
- Added a focused regression test for the pass-4 handoff.
- Documented the handoff and replay command in `docs/skill-route-discovery.md`.

## Validation

- `$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k 20260708T010200`
  - Passed: 1 test.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "pass4 and completion"`
  - Passed: 22 tests.

## Review Notes

- No external repository clone, install, runtime execution, provider launch,
  network call, promotion, push, or restart was performed.
- `docs/self-model.md` was read and left unchanged because the existing
  preference already supports rollback-backed, locally validated behavior
  changes and no route-specific correction was needed.
- Hy3 evidence remains preflight-only. The route records excluded provider and
  harness lanes as denied labels; it does not grant those lanes.
