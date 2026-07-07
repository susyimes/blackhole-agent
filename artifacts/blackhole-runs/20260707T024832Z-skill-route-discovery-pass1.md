# Skill Route Discovery Pass 1

Source digest: `github-growth-20260707T024834.700892Z`
Branch: `codex/blackhole-evolve/20260707T024921.776585-run-a-local-skill-route-discovery-validation-for`
Rollback ref: `refs/rollback/20260707T024832Z-skill-route-discovery-pass1`

## Evidence Review

- `reverse-flow-skill` exposes a Codex and AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, install examples, and run examples. It is local skill-route evidence only.
- `Agents-A1`, `Fundamental-Ava`, and `shepherd` are general agent, evaluation, runtime, or reversible-workflow projects. They require `agent_harness_eval_required` before any implementation lane.
- The workflow-usecase proposal has workflow-topic evidence but no explicit skill package signal, so it stays in the agent-harness evaluation boundary.

## Hypothesis

The active pass-1 controller surface should recognize this exact digest instead of falling back to stale generic skill, game, and state-handoff proposal IDs. Reverse-flow should map to a bounded local test lane; general-agent and workflow-usecase signals should remain harness-gated.

## Local Change

- Added `github-growth-20260707T024834.700892Z` recognition in the pass-1 skill-route lane.
- Added a frozen fixture for the current digest.
- Added a regression proving the lane is ready, body-free, activation-free, and split between skill-route and agent-harness evaluation families.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260707T024834`
- `pytest tests/test_skill_routing.py -q -k "skill_route_discovery_current_digest_20260707T024834 or current_digest_20260706T054239_routes_mixed_evidence_packet or current_digest_20260706T060238_pass2_routes_current_proposals"`
- `pytest tests/test_skill_routing.py -q`

All validation passed.

## Review Notes

- Self-model unchanged. It already prefers rollback-backed, locally validated behavior changes over validation-only reports, which matches this run.
- No external skill activation, upstream install, provider launch, external harness execution, remote execution, profile write, or memory write was added.
- External evidence was reviewed only from the proposal URLs carried by the capability window.
