# Skill Route Discovery Pass 2 Current Window

- Source digest: `github-growth-20260703T183923.572332Z`
- Branch: `codex/blackhole-evolve/20260703T184010.447382-add-a-bounded-local-skill-route-discovery-valida`
- Rollback point: `artifacts/rollback/20260703T183921Z-skill-route-discovery-pass2-current-window/rollback-point.md`
- Rollback ref: `refs/rollback/20260703T183921Z-skill-route-discovery-pass2-current-window`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF framing, and install/run examples.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with `SKILL.md`, `skill.yml`, references, scripts/evals, source-citation workflow, and advice-boundary language.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent apprenticeship/evaluation project without a `skill_route_discovery` hint in the frozen digest.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model/benchmark project without a `skill_route_discovery` hint in the frozen digest.

## Hypothesis

The current pass-2 window should expose an operator-visible local lane instead of only another isolated fixture:
Codex-oriented skill workflow evidence must route through `skill_route_discovery_first` and stay bounded to
documentation, config, test, or code_patch; generic skill workflow evidence should document and preflight the
same bounded lane envelope; general agent projects without skill workflow signals should remain
`agent_harness_eval_required` with no direct runtime or code_patch lane before local harness evidence exists.

## Changes

- Registered `github-growth-20260703T183923.572332Z` in the pass-2 local validation lane.
- Added a frozen current-window digest fixture for reverse-flow-skill, zhengxi-views, agent-apprenticeship, and Qwen-AgentWorld.
- Added regression coverage for the top-level lane, focused review lane, adjacent harness rows, body-free export constraints, and runtime/provider denial flags.
- Documented the new pass-2 interpretation in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T183923`
- `python -m pytest tests/test_skill_routing.py -q -k "20260703T183923 or 20260703T171922 or 20260703T004121"`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
- `python -m pytest tests/test_skill_routing.py -q`

All listed commands passed.

## Review Notes

- No self-model change: the existing preference already supports rollback-backed, locally validated behavior changes and a narrow safety boundary.
- No restart, push, promotion, provider launch, external harness execution, external skill activation, or remote execution was performed.
- Final gates remain controller-computed; this pass only adds bounded local route evidence and replayable validation.
