# Skill Route Discovery Pass 3 Run Note

- Source digest: `github-growth-20260702T064714.829371Z`
- Branch: `codex/blackhole-evolve/20260702T064809.305864-create-a-bounded-local-skill-route-discovery-val`
- Rollback artifact: `artifacts/rollback-20260702T064809Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T064809Z-skill-route-discovery-pass3`

## Focused Evidence

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes `SKILL.md`, `skill.yml`, references, scripts, evals, source-citation framing, and non-investment-advice limits. Interpreted only as source-cited skill-route evidence.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public repository frames life-science workflows as agent skills and exposes skill/workflow/catalog signals. Interpreted only as skill/workflow route evidence.

## Hypothesis

Current pass-3 skill-route evidence should have an operator-visible validation-before-activation lane for the active proposal names. Skill/workflow repositories may map only to documentation, config, test, or code_patch with local validation required. General-agent projects without skill workflow hints must remain behind `agent_harness_eval_required` with no direct lanes before local harness evidence exists.

## Local Changes

- Added current digest `github-growth-20260702T064714.829371Z` handling to `current_digest_pass3_activation_review_lane`.
- Added explicit aggregate general-agent fields: `direct_allowed_lanes_before_eval: []`, `allowed_local_lanes_after_eval`, `direct_runtime_route_allowed: false`, and `direct_code_patch_route_allowed: false`.
- Added a frozen body-free current digest fixture for pass 3.
- Added focused regression coverage for zhengxi, BioNeMo, Qwen-AgentWorld, and Fundamental-Ava routing.
- Updated route documentation for the validation-before-activation contract.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260702T064714`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_harness_eval.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

All validation commands passed.

## Review Notes

- No external skill activation, install, provider launch, external harness execution, remote execution, profile write, memory write, raw URL export, replay-command export, or upstream-body export was added.
- The self-model was read and left unchanged because its current preference already matched this run: reversible local behavior improvements are preferred when rollback-backed and locally validated.
