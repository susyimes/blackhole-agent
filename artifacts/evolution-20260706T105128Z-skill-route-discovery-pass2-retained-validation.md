# Skill Route Discovery Pass 2 Retained Validation

- Source digest: `github-growth-20260706T105129.764356Z`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T105128Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260706T105128Z-skill-route-discovery-pass2/rollback-point.md`
- Branch: `codex/blackhole-evolve/20260706T105210.949524-run-a-bounded-local-skill-route-discovery-valida`

## Evidence Read

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI-agent skill package with a local sandbox reverse-flow phase workflow and install/run pressure. Local lesson: keep the phase workflow as route evidence only until bounded local validation passes.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent benchmark/world-model project with evaluation and simulation claims. Local lesson: route through agent-harness evaluation before any behavior adoption.
- `https://github.com/shepherd-agents/shepherd`: public runtime substrate emphasizing retained outputs, reversible traces, review, and selection/discard before file application. Local lesson: expose retained validation metadata before activation.

## Hypothesis

Pass-2 skill-route discovery should expose an operator-visible retained validation packet: selected reverse-flow skill evidence maps to bounded local lanes, adjacent general-agent repositories remain queued for local harness evaluation, and activation stays impossible until replay metadata and phase gates are ready.

## Changes

- Added `skill_route_discovery_pass2_retained_validation_packet` to the route map.
- Added current digest fixture `current_digest_20260706T105129_pass2_local_validation_lane.json`.
- Added regression coverage for the retained packet, hashed replay command, phase gates, and agent-harness queue.
- Documented the packet in `docs/architecture.md`.

## Self-Model

Left unchanged. The existing self-model already supports rollback-backed local experiments while keeping offensive behavior, abuse, unauthorized access, and privacy leakage review-only. This run added behavior and tests rather than changing the self-description.

## Safety Notes

- No upstream skill code was cloned, installed, imported, or executed.
- No provider runtime, external harness, remote execution, profile write, memory write, push, promotion, or restart was performed.
- Raw upstream URLs and raw replay commands are not exported from the retained packet.
