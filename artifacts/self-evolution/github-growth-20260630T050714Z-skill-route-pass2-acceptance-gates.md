# Skill Route Discovery Pass 2 Acceptance Gates

- source_digest: github-growth-20260630T050714.525014Z
- capability_slice: Convert skill and route evidence into bounded local lanes that can be validated before activation.
- rollback_artifact: artifacts/rollback-20260630T050840Z.md
- rollback_ref: refs/blackhole-rollback/20260630T050840Z

## Evidence

- https://github.com/lyra81604/zhengxi-views exposes an explicit skill package shape, including SKILL.md, skill.yml, references, scripts, evals, and source-citation boundaries.
- https://github.com/QwenLM/Qwen-AgentWorld is general-agent benchmark/model evidence, not a local skill workflow route.

## Hypothesis

Pass-2 operator handoff is safer and more replayable when the proposal acceptance contract shows which local skill-route lanes were accepted, which upstream lane pressure was discarded, and why adjacent general-agent evidence remains gated through agent_harness_eval.

## Change

- Preserved unsupported upstream lane pressure as optional metadata on skill-route candidates.
- Extended the pass-2 proposal acceptance contract with aggregate skill acceptance gates and a separate adjacent agent-harness gate.
- Added focused assertions for accepted lanes, rejected upstream lanes, and the adjacent Qwen-AgentWorld-style gate.
- Documented the pass-2 acceptance gate behavior.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_pass2_validation_lane_keeps_agent_eval_adjacent`
- `python -m pytest tests/test_skill_routing.py -q -k "current_pass2_validation_lane or current_run_pass2_local_validation_lane or current_window_pass2_route_classification"`
- `python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
- `python -m pytest tests/test_docs_contracts.py -q`
- `python -m pytest tests/test_skill_routing.py -q`

All validation passed.

## Review Notes

- Self-model was read and left unchanged; it already described rollback-backed local evolution with narrow safety boundaries.
- No external skill code, provider runtime, harness execution, remote execution, install, profile write, or memory write was activated.
- Raw evidence URLs remain omitted from controller outputs; unsupported lane pressure is represented only as bounded lane names.
