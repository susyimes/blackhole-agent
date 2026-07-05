# Skill Route Discovery Pass 2

Source digest: github-growth-20260705T124958.128997Z

Capability slice: skill-route-discovery, pass 2 of 4.

Hypothesis:

The active pass-2 window should expose an operator-visible local validation lane for reverse-flow-skill while keeping adjacent general-agent projects behind `agent_harness_eval_required`. Repository-level evidence should also carry bounded uncertainty labels so lack of details or missing local harness fixtures does not silently look like activation readiness.

Evidence reviewed:

- `lingbol088-spec/reverse-flow-skill`: public repository describes a Codex/AI Agent skill workflow, local sandbox framing, `skills/reverse-flow/SKILL.md`, scripts, and install/run examples.
- `QwenLM/Qwen-AgentWorld`: public repository presents a general agent world-model/benchmark project.
- `TianhangZhuzth/Fundamental-Ava`: public repository presents a general autonomous/collaborative agent project.

Change:

- Added the active digest id `github-growth-20260705T124958.128997Z` to the pass-2 skill-route operator lane.
- Added digest-specific active proposal ids for the current supervisor window.
- Added `route_uncertainty` labels to pass-2 skill-route and adjacent general-agent rows.
- Added a regression test confirming reverse-flow maps only to documentation/config/test/code_patch after validation, while Qwen-AgentWorld and Fundamental-Ava remain `agent_harness_eval_required` with no direct runtime or implementation route.

Validation:

- `python -m pytest tests/test_github_growth.py -q -k "current_pass2_operator_lane_routes_124958 or current_pass2_skill_route_operator_lane"`: passed, 2 tests.
- `python -m pytest tests/test_proposal_eval.py -q -k route_hint_lane_map`: passed, 3 tests.
- `python -m pytest tests/test_github_growth.py -q`: passed, 101 tests.

Review notes:

- No upstream code was cloned, installed, executed, or activated.
- Raw GitHub URLs and upstream bodies remain excluded from the operator lane output.
- The self-model was read and left unchanged because it already describes the rollback-backed local-validation preference used by this run.
