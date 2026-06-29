# Skill Route Discovery Pass 3 Activation Review

Source digest: `github-growth-20260629T093324.244697Z`
Branch: `codex/blackhole-evolve/20260629T093415.832128-add-a-bounded-local-skill-route-discovery-valida`
Rollback artifact: `artifacts/rollback-20260629T093323Z-skill-route-discovery-pass3.md`
Rollback ref: `refs/rollback/blackhole-agent/20260629T093323Z-skill-route-discovery-pass3`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

The digest evidence was sufficient for a local replay fixture. No upstream code
was cloned, installed, executed, imported, or activated.

## Hypothesis

The pass-3 skill-route-discovery window needs an operator-visible activation
review packet, not another standalone route fixture. The packet should bind the
active proposals before pass 4:

- zhengxi-views-style skill metadata selects only the local `test` lane.
- COMPASS-style skill ecosystem handoff selects only the local `documentation`
  checklist lane before profile, memory, config, or code changes.
- Qwen-AgentWorld and looper stay adjacent as `agent_harness_eval_required`
  before documentation, test, or code_patch adoption.

## Local Changes

- Added a current-digest branch in
  `skill_route_discovery_pass3_current_wake_acceptance_packet`.
- Added a frozen pass-3 fixture for the current source digest.
- Added a regression test proving bounded local lanes, selected evidence item
  IDs, body-free output, denied activation, and eval-only adjacent
  general-agent handling.
- Updated `docs/skill-route-discovery.md` with the pass-3 operator contract.

The self-model was left unchanged because it already describes the relevant
preference for rollback-backed, locally validated behavior changes.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260629T093324 or pass3_current_wake_acceptance_packet"`: passed
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed

## Review Notes

- The new packet does not export raw GitHub URLs, replay commands, target paths,
  or upstream bodies.
- Unsupported install, provider runtime, and runtime execution pressure is
  excluded from allowed local lanes.
- External skill activation, external agent activation, external harness
  execution, provider launch, profile writes, memory writes, and remote
  execution remain denied.
