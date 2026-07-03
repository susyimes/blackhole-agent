# Run Notes

- Source digest: `github-growth-20260703T031812.587978Z`
- Active validation fixture: `tests/fixtures/skill_route_discovery/current_digest_20260703T025735_pass2_validation_lane.json`
- Rollback artifact: `artifacts/blackhole-runs/20260703T032123Z/rollback.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T032123Z`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`
- `https://github.com/QwenLM/Qwen-AgentWorld`

## Hypothesis

Pass 3 of the `skill-route-discovery` slice should expose an operator-visible
activation review packet for the active proposal IDs. Codex-adjacent skill
repositories should classify as `skill_route_discovery_first` before any local
workflow change. General-agent and workflow-only repository evidence should stay
behind `agent_harness_eval_required` with no direct implementation lane.

## Changes

- Specialized the pass-3 activation review lane for
  `github-growth-20260703T025735.929695Z`.
- Added `codex_workflow_gate_policy` metadata and a row-level
  `skill_route_discovery_first` decision for `p2-codex-workflow-gate-discovery`.
- Kept workflow-only and general-agent evidence under
  `p3-agent-harness-eval-fixtures` with empty direct lanes before local harness
  evaluation.
- Documented the pass-3 interpretation in `docs/skill-route-discovery.md`.

## Validation

- `PYTHONPATH=src pytest tests/test_skill_routing.py -q -k "20260703_pass3_exposes_discovery_first_gate or 20260703T025735 or current_digest_pass3_activation_review"`: passed, 2 passed.
- `PYTHONPATH=src pytest tests/test_docs_contracts.py -q`: passed, 11 passed.
- `PYTHONPATH=src pytest tests/test_skill_routing.py -q`: passed, 195 passed.

## Review Notes

- No runtime action, external skill activation, provider launch, remote
  execution, raw URL export, raw replay command export, or upstream body export
  is enabled by this change.
- `docs/self-model.md` was read and left unchanged because the current run
  needed a concrete route behavior improvement, and the existing self-model did
  not contradict the bounded local-validation implementation.
