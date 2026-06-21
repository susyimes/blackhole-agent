# Skill Route Discovery Pass 3 Handoff

- Source digest: `github-growth-20260621T023207.792003Z`
- Capability window: `skill-route-discovery`, pass 3 of 4
- Branch: `codex/blackhole-evolve/20260621T023259.428361-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback artifact: `artifacts/rollback/20260621T023207Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/20260621T023207Z-skill-route-discovery-pass3`

## Evidence

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/omnigent-ai/omnigent`

The useful lesson remains bounded local skill-route discovery. Mixed
Codex/workflow/skill evidence should continue through `skill_route_discovery`
before any broader agent-harness lane, and domain or ecosystem skill
repositories should produce only documentation, config, test, or code_patch
lanes.

## Hypothesis

Pass 3 needs an operator-visible handoff packet for the final pass, not another
standalone corpus fixture. The existing harness already selects a local `test`
lane for FableCodex and Three.js-style workflow/game evidence and queues a
local `config` lane for COMPASS-style state handoff. A compact pass-3 packet
can make that final-pass workload replayable without exporting raw URLs,
upstream bodies, target paths, or allowing runtime execution.

## Change

- Added `pass3_handoff_packet` to `skill_route_discovery_lane`.
- The packet is derived from `current_action`,
  `pass_validation_replay_queue`, and `mixed_local_lane_probe`.
- It reports selected and queued bounded local lanes, route profiles, selected
  digest item IDs, candidate source hashes, replay commands, and the blocked
  secondary agent-harness lane.
- It denies runtime action, external skill activation, external skill code,
  external harness execution, provider launch, remote execution, raw evidence
  URLs, raw source URLs, raw target paths, and upstream body export.
- Updated `docs/skill-route-discovery.md` and the docs contract test.

## Self-Model

`docs/self-model.md` was read and left unchanged. It already states the
current preference for rollback-backed, locally validated behavior changes and
the narrow safety boundary. This run did not add a new behavior-shaping
self-description beyond the concrete harness packet.

## Validation

Validation is recorded in the final run response.

## Review Notes

The packet is body-free and term/profile derived. It does not inspect upstream
skill bodies and does not prove upstream implementation parity. The secondary
`agent_harness_eval_after_local_corroboration` lane remains blocked until a
later local corroboration or general agent-project claim exists.
