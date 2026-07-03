# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260703T072049.930896Z`
- Branch: `codex/blackhole-evolve/20260703T072218.710956-run-bounded-skill-route-discovery-against-the-zh`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260703T072049Z-rollback.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T072049Z-skill-route-discovery-pass3`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: reviewed as a public Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, source-cited workflow language, and explicit advice-boundary framing.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: reviewed as public Codex / AI Agent skill-route evidence with `skills/reverse-flow/SKILL.md`, references, scripts, local sandbox or training context, and workflow-gate language.
- `https://github.com/QwenLM/Qwen-AgentWorld`: reviewed as a general agent project signal, not a local skill workflow signal.

## Hypothesis

The active pass-3 slice should expose an operator-visible route-to-validation lane
for this digest. `zhengxi-views` and `reverse-flow-skill` can become bounded
`skill_route_discovery` rows that select local `test`, while `Qwen-AgentWorld`
must remain adjacent `agent_harness_eval_required` with no implementation lane
selected before local harness evaluation.

## Change

- Added `github-growth-20260703T072049.930896Z` handling to
  `current_digest_pass3_route_to_validation_lane`.
- Added a frozen body-free fixture for the current digest.
- Added a regression asserting:
  - zhengxi maps only to documentation/config/test/code_patch and selects local `test`;
  - reverse-flow preserves `skill_route_discovery_first` before Codex workflow handling;
  - Qwen-AgentWorld remains `agent_harness_eval_required`, with no direct runtime or code patch route.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260703T072049 or 20260703T060050_pass3_routes_current_window or 20260703T044050_pass3_routes_to_validation_lane"
```

Result: passed, `3 passed, 203 deselected`.

## Review Notes

- The self-model was read and left unchanged. It already matches this run's choice to prefer a rollback-backed, locally validated behavior path over another validation-report-only artifact.
- No upstream code, skill package, provider runtime, external harness, or remote execution was run.
- Raw source URLs remain absent from the exported controller packet; the fixture stores source URLs as local evidence inputs only.

