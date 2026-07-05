# Evolution Run: skill-route-discovery pass 2 secondary harness checklist

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: treated as Codex-oriented skill workflow evidence that can enter only bounded local skill-route lanes.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: treated as generic skill/workflow route evidence that can enter only bounded local skill-route lanes.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: treated as adjacent general-agent project evidence that requires a local agent-harness fixture before implementation lanes open.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: carried as adjacent workflow/usecase evidence; no direct runtime or provider action was added.

## Hypothesis

Pass-2 skill-route handoff is more useful to an operator if the proposal-synthesis lane map exposes the same secondary harness checklist described by the architecture docs: skill/workflow rows can continue through documentation, config, test, or code_patch validation, while adjacent general-agent rows are blocked until a local harness fixture declares a runnable scenario, expected output, pass/fail signal, rollback artifact, and non-secret config.

## Changes

- Added `current_pass2_secondary_harness_checklist` to the proposal lane map.
- Embedded the checklist in `current_pass2_activation_readiness` and `current_pass2_lane_handoff`.
- Updated pass-2 active proposal IDs to the current skill-route discovery window.
- Added regression coverage for reverse-flow, BioNeMo, Qwen-AgentWorld, and Fundamental-Ava-style routing.
- Created rollback artifact `artifacts/rollback/20260705T044816Z-skill-route-discovery-pass2.md` and rollback ref `refs/blackhole-rollback/20260705T044816Z-skill-route-discovery-pass2`.

## Validation

- `python -m pytest tests/test_github_growth.py tests/test_proposal_eval.py -q -k "current_pass2_lane_handoff or current_pass2_skill_route_window or pass2_route_evidence_lane_source or pass2_activation_readiness"`: passed, 4 tests.
- `python -m pytest tests/test_github_growth.py tests/test_proposal_eval.py -q`: passed, 129 tests.

## Review Notes

- No external repository code was cloned, executed, installed, or activated.
- The self-model was read and left unchanged because it already matched the run evidence: prefer rollback-backed, locally validated behavior improvements over validation-report-only work.
- Adjacent general-agent rows still do not inherit `skill_route_discovery`, launch harnesses, start providers, perform remote execution, or export raw source URLs or upstream bodies.
