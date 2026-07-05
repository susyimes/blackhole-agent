# Skill Route Discovery Pass 4 Current Window

Source digest: github-growth-20260705T133637.071370Z

## Hypothesis

The current capability window has enough local route evidence to complete as an operator-visible pass-4 handoff:
reverse-flow-skill is a Codex/agent skill workflow candidate that should route through bounded local lanes, while
Qwen-AgentWorld, Fundamental-Ava, and Agents-A1 remain adjacent general-agent projects requiring harness evaluation
before any implementation or runtime activation.

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill: public Codex/AI Agent skill package with `skills/reverse-flow`,
  local sandbox/CTF framing, workflow steps, install examples, and scripts.
- https://github.com/QwenLM/Qwen-AgentWorld: general agent world-model and AgentWorldBench project across agent domains.
- https://github.com/TianhangZhuzth/Fundamental-Ava: autonomous/collaborative agent research infrastructure under active development.
- https://github.com/InternScience/Agents-A1: general Python agent research project.

## Change

- Registered `github-growth-20260705T133637.071370Z` in the pass-4 current-digest dispatcher.
- Extended the July 5 reverse-flow completion helper with current-window proposal IDs, replay marker, expected adjacent
  agent projects, and body-free anchoring proposal IDs.
- Added a frozen current-digest fixture and regression that checks:
  - reverse-flow selects bounded `test` and `documentation` local lanes only;
  - install/runtime pressure is downgraded;
  - Qwen-AgentWorld, Fundamental-Ava, and Agents-A1 stay in `agent_harness_eval_required`;
  - no raw GitHub URLs, replay commands, target paths, upstream bodies, runtime execution, or activation authority leak into the handoff.

## Rollback

- Ref: `refs/blackhole/rollback/20260705T133635Z-skill-route-discovery-pass4`
- Artifact: `artifacts/rollback/20260705T133635Z-skill-route-discovery-pass4-current-window/rollback-point.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260705T133637`
  - Result: 1 passed, 304 deselected.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: 305 passed.

## Review Notes

- Self-model left unchanged: the existing preference for rollback-backed, locally validated behavior changes matches this run.
- No upstream code was cloned, installed, executed, or activated.
- No restart, push, promotion, provider launch, profile write, or memory write was performed by this kernel.
