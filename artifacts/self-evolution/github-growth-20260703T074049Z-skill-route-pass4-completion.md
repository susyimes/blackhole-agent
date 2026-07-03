# Skill Route Discovery Pass 4 Completion

- Source digest: `github-growth-20260703T074049.962015Z`
- Branch: `codex/blackhole-evolve/20260703T074153.401607-add-or-strengthen-local-tests-for-skill-route-di`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260703T074049Z-rollback.md`
- Rollback ref: `refs/blackhole-rollbacks/20260703T074153-skill-route-discovery-pass4`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: reviewed narrowly as public Codex and AI Agent skill-route evidence with reverse-flow skill layout, local sandbox framing, scripts, and workflow-gate language.
- `https://github.com/lyra81604/zhengxi-views`: carried from the active window as public Agent Skill evidence with source-cited workflow and validation boundaries.
- `Qwen-AgentWorld` remains general-agent evidence from the digest/proposal context, not a skill workflow route.

## Hypothesis

The current fourth pass should expose a completion handoff and final closure for the skill-route-discovery window. Reverse-flow fork evidence and zhengxi skill evidence can close only through bounded local lanes with local validation required. General-agent evidence must remain adjacent `agent_harness_eval_required` before any documentation, test, or code_patch follow-up is selected.

## Change

- Added digest-specific pass-4 completion handling for `github-growth-20260703T074049.962015Z`.
- Added a final-closure path derived from the completion handoff so pass-4 closure does not fall back to older default route specs.
- Added a frozen, body-free fixture for the reverse-flow fork cluster, zhengxi skill evidence, and Qwen general-agent evidence.
- Added a regression asserting:
  - reverse-flow fork rows keep `skill_route_discovery_first`;
  - selected skill lanes remain within documentation, config, test, or code_patch;
  - local validation remains required;
  - Qwen stays behind `agent_harness_eval_required`;
  - raw URLs and replay commands are not exported from the operator surfaces.
- Updated `docs/skill-route-discovery.md` with the expected pass-4 interpretation path.

## Validation

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k current_digest_20260703T074049
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "current_digest_20260703T074049 or current_digest_20260703T072049 or current_digest_20260703T070049 or current_digest_20260703T050050"
$env:PYTHONPATH='src'; python -m compileall -q src\blackhole_agent\skill_routing.py
```

Results:

- Focused regression: passed, `1 passed, 206 deselected`.
- Recent skill-route slice: passed, `4 passed, 203 deselected`.
- Compile check: passed.

## Review Notes

- The self-model was read and left unchanged. It already states the relevant preference: prefer rollback-backed, locally validated local evolution over validation-report-only work.
- No upstream code, skill package, provider runtime, external harness, remote execution, install, or activation path was run.
- Raw evidence URLs are present only in the local fixture input. The generated completion, closure, and operator packet keep raw source URL and raw replay-command export denied.
