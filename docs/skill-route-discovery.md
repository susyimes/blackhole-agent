# Skill Route Discovery (removed)

This document previously recorded the `skill_route_discovery` capability
pipeline: a generated lane machinery of classifier stages, route profiles,
bounded local-apply lanes, focused-validation windows, residual-adjacent
queues, and nested continue-cascade / pin-call packaging, together with the
`agent_harness_eval` fixture evaluator lanes.

That machinery has been demolished and no longer exists in the runtime:

- `src/blackhole_agent/skill_routing.py` and `src/blackhole_agent/harness_eval.py`
  are deleted, along with their dedicated test suites.
- `github_growth` no longer emits `skill_route_discovery_capability_pipeline`;
  digests carry only the compact `evolution_route` surface from
  `blackhole_agent.evolution_route`, which redirects growth to the Capability
  Compounder when the durable ledger is ready and honestly reports
  `ledger_not_ready` otherwise.
- `proposal_synthesis` route hints are reduced to `provider_config_preflight`
  and `governance_policy`, each mapped only to
  documentation/config/test/code_patch lanes.
- Harness activation gating survives as a native, local-eval-only decision in
  `blackhole_agent.capability_compounder:harness_activation_gate_decision`.
  Only the clean `none` failure mode activates; external harness execution is
  never allowed.
- `BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE=1` no longer revives any lane
  pipeline; it only selects the plain digest/plan supervisor surface.

The working growth substrate is the compounded capability ledger in
`capabilities/ledger.json`: capabilities are registered with invocable proof
commands, proved, and composed. See `docs/architecture.md` (Evolution Route
and Capability Compounder) and `docs/unbound-v2.md` (Capability Compounder)
for the current contract.

The full historical text remains available in Git history prior to the
demolition milestones.
