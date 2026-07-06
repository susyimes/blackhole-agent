# Blackhole Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260706T042239.700823Z`
- Branch: `codex/blackhole-evolve/20260706T042323.913435-create-a-bounded-local-skill-route-discovery-val`
- Rollback artifact: `artifacts/rollback/20260706T042237Z-skill-route-discovery-pass1/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T042237Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and CTF framing, install/run examples, and staged reverse workflow language.
- `https://github.com/InternScience/Agents-A1`: general agentic model project with long-horizon trajectory, evaluation, model, and benchmark claims.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model and benchmark project with environment simulation and evaluation claims.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent simulation project with memory, collaboration, social simulation, experiments, and workflow claims.

## Hypothesis

Pass 1 should expose the current active proposal IDs as a bounded local lane:
reverse-flow-skill enters `skill_route_discovery` first, while Agents-A1,
Qwen-AgentWorld, and Fundamental-Ava stay in an `agent_harness_eval_required`
queue before any direct implementation route. This improves supervisor handoff
for the active digest without importing upstream code or widening runtime
authority.

## Changes

- Added the `github-growth-20260706T042239.700823Z` branch in
  `current_digest_pass1_validation_lane`.
- Added a frozen fixture for the current digest with one reverse-flow skill
  route item and three general-agent adjacent items.
- Added regression assertions for active proposal IDs, bounded local lanes,
  adjacent harness gates, operator validation lane readiness, and raw URL /
  runtime denial.
- Documented the current digest in `docs/skill-route-discovery.md`.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k 20260706T042239`
  - Passed: 1 passed, 320 deselected.
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260706T042239 or 20260706T030239 or 20260706T032238"`
  - Passed: 3 passed, 318 deselected.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
  - Passed: 4 passed, 238 deselected.

## Review Notes

- Self-model left unchanged. It already says local evolution should prefer
  rollback-backed, locally validated behavior changes while keeping offensive
  behavior and privacy leakage review-only.
- `p4_shepherd_workflow_probe` is represented as a workflow-probe gate only.
  No Shepherd-specific implementation, controller route, scheduler change, or
  external execution path was added.
- The pass keeps raw upstream URLs, raw replay commands, upstream bodies,
  external skill activation, external agent activation, external harness
  execution, provider launch, remote execution, profile writes, memory writes,
  and runtime action denied.
