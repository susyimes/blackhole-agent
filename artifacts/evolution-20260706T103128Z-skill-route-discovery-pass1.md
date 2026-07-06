# Evolution Run: skill-route-discovery pass 1 current digest

Source digest: `github-growth-20260706T103129.849391Z`

Rollback point:
`artifacts/rollback/20260706T103128Z-skill-route-discovery-pass1-current-digest/rollback-point.md`

## Evidence

- `380359884/reverse-flow-skill` is public fork-lineage evidence for a Codex/AI Agent skill workflow with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox defaults, install examples, run examples, and staged workflow language.
- `lingbol088-spec/reverse-flow-skill` is the upstream repository for the same public skill workflow pattern.
- Agents-A1, Qwen-AgentWorld, Fundamental-Ava, and shepherd are general-agent evidence without explicit local skill workflow route hints.

## Hypothesis

Current pass-1 evidence should become an operator-visible local validation lane before activation. Reverse-flow-style skill workflow evidence may map only to documentation, config, test, or code_patch with `local_validation_required=true`. General-agent projects must stay behind `agent_harness_eval_required` with no direct implementation lane before local harness evaluation.

## Changes

- Added the frozen current-digest fixture `current_digest_20260706T103129_pass1_validation_lane.json`.
- Added a source-digest-specific pass-1 route specification for proposal IDs `p1_reverse_flow_skill_route_discovery` through `p5_no_direct_external_behavior_adoption`.
- Added regression coverage for bounded local lanes, selected item IDs, body-free output, activation denial, and the adjacent general-agent harness gate.
- Documented the current digest handling in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T103129`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 334 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 11 tests.

## Review Notes

- No self-model edit. The existing self-model already supports rollback-backed local experiments and the narrow offensive/privacy review boundary used by this run.
- No external code was installed, cloned, executed, or activated. Raw upstream URLs remain out of the lane output.
