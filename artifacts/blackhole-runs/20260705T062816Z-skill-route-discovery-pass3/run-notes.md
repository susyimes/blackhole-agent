# Skill Route Discovery Pass 3

Source digest: `github-growth-20260705T062818.952201Z`

## Evidence Read

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow with local sandbox, install, and script examples. Interpreted as skill-route evidence only; upstream install or execution remains denied.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public domain-specific agent toolkit with skill/workflow/catalog signals. Interpreted as generic skill-workflow route evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: public general-agent project evidence without direct skill-workflow activation authority. Interpreted as adjacent agent-harness evaluation evidence.
- Agents-A1 fork proposal: repeated forks should strengthen one local harness-eval candidate, not create redundant implementation proposals.

## Hypothesis

The pass-3 operator surface is more useful if repeated general-agent forks are collapsed into one `agent_harness_eval_required` candidate with all item IDs preserved. This improves controller review without importing upstream code, running upstream harnesses, or enabling runtime behavior.

## Changes

- Added `agent_harness_fork_cluster_eval_queue` to `agent_harness_eval_lane`.
- Added an Agents-A1 fork-cluster fixture and direct regression test.
- Documented the fork-cluster queue in `docs/architecture.md`.
- Self-model unchanged. It already supports rollback-backed, locally validated behavior changes and did not need a revision for this run.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "agents_a1_fork_cluster or agent_harness_eval_lane"`: passed, 4 tests.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures"`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k "skill_route_discovery or architecture"`: passed, 3 tests.

## Review Notes

- The new queue exports item IDs and hashes only; raw GitHub URLs and upstream bodies are not exported.
- Direct runtime route, direct code patch route, external harness execution, provider launch, and remote execution remain disabled before local validation.
- Rollback ref: `refs/blackhole/rollback/20260705T062816Z-skill-route-discovery-pass3`.
