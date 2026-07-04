# Skill Route Discovery Pass 1

- Source digest: github-growth-20260704T134434.634232Z
- Theme: skill-route-discovery
- Capability slice: Convert skill and route evidence into bounded local lanes that can be validated before activation.
- Rollback artifact: artifacts/rollback-20260704T134432Z-skill-route-discovery-pass1.md

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/reverse-flow`, workflow framing, scripts, and install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill with source-cited research, fund-data references, and explicit research/advice boundary language.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: public agent-assisted Blender/Seedance workflow collection without a local skill-route hint.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent research project without a local skill-route hint.

## Hypothesis

The current digest should open a pass-1 validation lane rather than another
standalone fixture. Skill-like evidence can enter `skill_route_discovery` only
through documentation, config, test, or code_patch lanes. Adjacent general
agent/workflow evidence should be held behind `agent_harness_eval_required`
before any implementation lane opens.

## Local Change

- Added a `github-growth-20260704T134434.634232Z` specialization to
  `current_digest_pass1_validation_lane`.
- Added a frozen current-digest fixture covering reverse-flow-skill,
  zhengxi-views, Awesome-Blender-Seedance-Workflow-Usecases, and Qwen-AgentWorld.
- Added a regression test for bounded skill lanes, Codex workflow-gate
  discovery-first handling, route matrix visibility, and adjacent harness-eval
  gating.
- Documented the current digest behavior in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T134434`
  - Result: 1 passed, 268 deselected.
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: 269 passed.
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: 11 passed.

## Review Notes

- Self-model was read and left unchanged; it already supports rollback-backed
  locally validated behavior changes and did not need a narrower or broader
  revision for this pass.
- No external skill activation, upstream install, provider launch, external
  harness execution, remote execution, profile write, or memory write was added.
- Raw upstream bodies and raw source URLs are not exported in the controller
  packet; selected item IDs and hashes remain the replay surface.
