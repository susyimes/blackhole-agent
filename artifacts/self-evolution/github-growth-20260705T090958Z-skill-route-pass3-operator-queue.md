# Skill Route Discovery Pass 3 Operator Queue

- Source digest: `github-growth-20260705T090958.166843Z`
- Capability slice: `skill-route-discovery`, pass 3 of 4
- Rollback artifact: `artifacts/rollback/20260705T091047Z-skill-route-discovery-pass3-reverse-flow-current-window/rollback-point.md`
- Rollback ref: `refs/rollback/20260705T091047Z-skill-route-discovery-pass3-reverse-flow-current-window`

## Evidence Checked

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/14457/reverse-flow-skill`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/TianhangZhuzth/Fundamental-Ava`
- `https://github.com/InternScience/Agents-A1`

The reverse-flow repositories expose Codex/agent skill workflow evidence with `skills/reverse-flow`, local sandbox framing, install examples, and scripts. The general-agent repositories carry benchmark, evaluation, model, or agent-project signals without explicit skill workflow route hints or local harness results.

## Hypothesis

The current pass should produce an operator-visible validation queue instead of only another standalone fixture: reverse-flow evidence becomes bounded documentation and test lanes, while Qwen-AgentWorld, Fundamental-Ava, and Agents-A1 remain in `agent_harness_eval_required` until local harness evidence exists.

## Local Change

- Added `current_20260705_090958` pass-3 routing in `src/blackhole_agent/skill_routing.py`.
- Added a frozen digest fixture for the current window.
- Added a regression test asserting bounded reverse-flow lanes, fork-lineage collapse, no runtime/provider/remote activation, and the adjacent general-agent queue.
- Left `docs/self-model.md` unchanged because it already supports validated local behavior changes and did not need new structure for this run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260705T090958 or 20260705T074818_pass3"`: passed
- `python -m pytest tests/test_skill_routing.py -q`: passed
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: passed

## Review Notes

- No external skill code is installed, imported, executed, or activated.
- Raw upstream URLs remain fixture input evidence only; emitted lane packets keep body-free diagnostics and hashes.
- General agent projects do not inherit skill-route lanes and cannot move to documentation, test, or code patch work before local harness evaluation.
