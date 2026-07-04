# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260704T085309.981717Z`
- Rollback point: `refs/blackhole-rollback/20260704T085307Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T085307Z-skill-route-discovery-pass3/rollback-point.md`
- Branch: `codex/blackhole-evolve/20260704T085405.500574-add-a-bounded-local-skill-route-discovery-valida`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Agent/Codex skill package with install and script examples. Local lesson: classify as skill-route evidence first, keep install/runtime pressure diagnostic-only.
- `https://github.com/lyra81604/zhengxi-views`: public source-cited Agent Skill repository. Local lesson: generic skill workflow evidence maps to documentation/config/test/code_patch lanes only after local validation.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: public general-agent projects without skill workflow route hints in this digest. Local lesson: keep behind `agent_harness_eval_required` with no direct lane before local harness evaluation.

## Hypothesis

The current pass-3 capability slice should expose an operator-visible route-to-validation lane for the active digest, instead of requiring the supervisor to infer route handling from older pass-3 fixtures. Reverse-flow skill evidence should preserve `skill_route_discovery_first`; generic skill workflow evidence should enter a documentation lane; general-agent evidence should remain adjacent and eval-only.

## Changes

- Added `github-growth-20260704T085309.981717Z` handling to the pass-3 route-to-validation lane.
- Added a frozen current-digest fixture for reverse-flow, zhengxi-views, Qwen-AgentWorld, and Fundamental-Ava.
- Added a regression asserting bounded local lanes, no runtime action, no raw source URL export, and the adjacent `agent_harness_eval_required` contract.
- Documented the operator replay command and current-digest route interpretation.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T085309
```

Passed: 1 passed, 256 deselected.

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260704T085309 or 20260704T083309 or 20260704T073310"
```

Passed: 3 passed, 254 deselected.

```powershell
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc
```

Passed: 2 passed, 9 deselected.
