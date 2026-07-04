# Skill Route Discovery Pass 1: Reverse-Flow Lane

- Source digest: `github-growth-20260704T150434.812972Z`
- Branch: `codex/blackhole-evolve/20260704T150529.595988-add-or-extend-local-tests-that-exercise-skill-ro`
- Rollback: `artifacts/rollback/20260704T150529Z-skill-route-discovery-pass1-reverse-flow/rollback-point.md`

## Evidence Reviewed

- `https://github.com/iamcaozhi/reverse-flow-skill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`

The reverse-flow repositories expose a Codex/AI Agent skill shape with SKILL.md
layout, scripts, and README install/run instructions. The `iamcaozhi` repository
is fork-lineage evidence for `lingbol088-spec/reverse-flow-skill`, so it should
collapse into one local discovery candidate instead of becoming a second
activation pressure source.

## Hypothesis

Skill-route discovery should preserve route profiles and unsupported upstream
action pressure through fork-lineage collapse. Upstream install, run, execute,
or runtime pressure should be diagnostic metadata only; accepted local lanes
remain documentation, config, test, or code_patch, with runtime action set to
`none`.

## Local Change

- Extended `ExternalSkillRepositorySummary` with `unsupported_lane_pressure`
  aliases for upstream action pressure.
- Preserved `route_profiles` and `unsupported_lane_pressure` when duplicate or
  fork-related skill candidates merge.
- Added a reverse-flow fork-lineage regression covering summary intake,
  lineage collapse, lane-map generation, and activation denial booleans.
- Documented the current pass interpretation in `docs/skill-route-discovery.md`.

Self-model decision: left unchanged. The current self-model already prefers
rollback-backed local behavior changes over report-only work while keeping
offensive behavior and privacy leakage outside autonomous activation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k reverse_flow_fork_lineage`
  - `1 passed, 271 deselected`
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery_summary_classifier or reverse_flow_fork_lineage or external_skill_route_discovery"`
  - `7 passed, 265 deselected`
- `python -m pytest tests/test_proposal_eval.py -q -k "reverse_flow_skill_route_probe or skill_route_discovery_enforces_lanes_refs_limits_and_uncertainty or current_pass3_operator_gate"`
  - `3 passed, 26 deselected`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`
  - `2 passed, 9 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - `272 passed`
- `python -m pytest tests/test_proposal_eval.py -q`
  - `29 passed`
- `python -m pytest tests/test_docs_contracts.py -q`
  - `11 passed`

## Review Notes

- No upstream code, install scripts, prompts, skill bodies, or runtime actions
  were adopted.
- General-agent evidence such as Qwen-AgentWorld remains an adjacent
  `agent_harness_eval_required` route and does not inherit skill-route lanes.
