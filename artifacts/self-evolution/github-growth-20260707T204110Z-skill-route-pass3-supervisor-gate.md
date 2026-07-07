# Skill Route Pass 3 Supervisor Gate

- Source digest: github-growth-20260707T204110.181515Z
- Capability slice: skill-route-discovery
- Pass: 3 of 4
- Rollback ref: refs/rollback/20260707T204108Z-skill-route-discovery-pass3-current-window
- Rollback artifact: artifacts/rollback/20260707T204108Z-skill-route-discovery-pass3-current-window/rollback-point.md

## Evidence

The current window carried reverse-flow-skill and rnskill as skill/workflow evidence, with Agents-A1 and Fundamental-Ava as adjacent general-agent projects. Narrow evidence review confirmed the reusable lesson: skill package signals should become bounded local replay lanes, while adjacent agent projects remain behind agent-harness evaluation.

## Hypothesis

Pass-3 already emits queue, probe, runbook, and control-plane surfaces, but operators still need a single replay gate that says whether the current lane can continue to pass 4 without activation. A body-free aggregate gate reduces inference work and makes blocked nested surfaces visible.

## Change

Added `skill_route_discovery_pass3_supervisor_activation_gate` to the pass-3 handoff packet. It aggregates replay queue readiness, proposal-lane mapping, local validation proof, promotion runbook, runner control plane, and adjacent agent holdback. It exports hashes for replay commands and keeps activation, push, restart, provider launch, remote execution, raw URLs, raw commands, and upstream bodies disabled.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3"`: passed
- `pytest tests/test_harness_eval.py tests/test_skill_routing.py -q -k "skill_route_discovery_lane or skill_route_discovery_pass3 or reverse_flow"`: passed

## Self-Model

`docs/self-model.md` was left unchanged. Its current preference already supports rollback-backed, locally validated behavior changes while keeping activation and unsafe routes outside the kernel.

## Review Notes

No offensive behavior, unauthorized access, or privacy-leakage route was added. Adjacent general-agent evidence remains gated to local harness evaluation.
