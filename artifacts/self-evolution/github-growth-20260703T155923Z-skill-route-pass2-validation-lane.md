# Skill Route Discovery Pass 2 Validation Lane

Source digest: `github-growth-20260703T155923.781249Z`

Capability slice: convert skill and route evidence into bounded local lanes that can be validated before activation.

## Evidence Interpretation

- `https://github.com/lingbol088-spec/reverse-flow-skill` presents a Codex / AI Agent skill workflow with local sandbox reverse-engineering framing, scripts, and workflow-gate pressure. Local lesson: Codex-oriented skill evidence must be discovered as a skill route first, not treated as permission to install, execute, or enter runtime routing.
- `https://github.com/lyra81604/zhengxi-views` presents a generic Agent Skill workflow with source-citation and advice-boundary metadata. Local lesson: generic skill workflow evidence can enter documentation, config, test, or code_patch lanes only after local validation.
- `https://github.com/Forsy-AI/agent-apprenticeship` and `https://github.com/QwenLM/Qwen-AgentWorld` are general agent project evidence without a skill workflow route hint. Local lesson: these stay in `agent_harness_eval_required` until a local harness gate produces concrete findings.

## Hypothesis

Adding an explicit pass-2 route surface for the current digest improves operator-visible continuity from pass 1 by proving the active proposals remain bounded before any runtime routing, provider launch, external harness execution, or direct code implementation lane is enabled.

## Changes

- Added `github-growth-20260703T155923.781249Z` recognition in `src/blackhole_agent/skill_routing.py`.
- Added three pass-2 proposal rows:
  - `p1-reverse-flow-skill-route-discovery`
  - `p2-generic-skill-workflow-route-fixture`
  - `p3-agent-harness-eval-for-general-agent-projects`
- Added frozen direct route and local harness fixtures for the active digest.
- Added focused tests for both the route-classification path and harness replay path.

## Rollback

Rollback point: `artifacts/rollback/20260703T155921Z-skill-route-discovery-pass2/rollback-point.json`

Local rollback ref: `refs/rollback/blackhole-agent/20260703T155921Z-skill-route-discovery-pass2`

Rollback remains explicit and destructive; the recorded commands are for operator or supervisor use only.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260703T155923`
- `pytest tests/test_harness_eval.py -q -k 20260703T155923`
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q`

Result: all passed.

## Review Notes

- Self-model unchanged. The existing preference for rollback-backed local evolution remains aligned with this pass.
- Raw upstream bodies, source URLs, replay commands, and target paths are not exported from the controller surfaces under test.
- General agent projects remain evaluation-only with `runtime_action: none`, `direct_code_patch_route_allowed: false`, and `external_harness_execution_allowed: false`.
