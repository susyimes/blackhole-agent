# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260703T153924.100531Z`
- Branch: `codex/blackhole-evolve/20260703T154022.470865-add-or-extend-local-tests-that-verify-codex-orie`
- Rollback: `artifacts/rollback/20260703T153921Z-skill-route-discovery-pass1-current-window/rollback-point.json`
- Theme: `skill-route-discovery`

## Evidence Interpretation

- `lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill package shape, local sandbox/CTF framing, scripts, and workflow language. Local lesson: classify it as `codex_workflow_gate` and require `skill_route_discovery_first` before broader workflow or agent handling.
- `lyra81604/zhengxi-views` exposes a non-Codex Agent Skill workflow with source-cited and advice-boundary metadata. Local lesson: classify it as `generic_skill_workflow` plus `source_cited_domain_research` inside the bounded skill-route lanes.
- `Forsy-AI/agent-apprenticeship` and `QwenLM/Qwen-AgentWorld` are general agent project evidence for this pass. Local lesson: keep them in `agent_harness_eval_required` with no direct runtime, code_patch, provider, external harness, remote, or external activation route before local harness evaluation.

## Hypothesis

The current pass should be replayable as a digest-specific lane so future scheduled runs can verify Codex-oriented skill workflow routing before broader agent handling, while preserving generic skill routing and the general-agent harness boundary.

## Changes

- Added source digest `github-growth-20260703T153924.100531Z` to the pass-1 skill-route lane mapping in `src/blackhole_agent/skill_routing.py`.
- Added `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260703T153924_pass1_validation_lane.json`.
- Added a named regression test for the digest and updated aggregate local fixture counts in `tests/test_harness_eval.py`.
- Documented the replay surface in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k 20260703T153924` passed.
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.

## Review Notes

- Self-model left unchanged. It already says to prefer rollback-backed, locally validated behavior changes over validation-report-only work, and this run followed that rule.
- No upstream code was cloned, installed, imported, or executed.
- Raw source URLs and upstream bodies are not exported from the replayed lane output.
- Activation, promotion, push, restart, and rollback execution remain supervisor or operator responsibilities.
