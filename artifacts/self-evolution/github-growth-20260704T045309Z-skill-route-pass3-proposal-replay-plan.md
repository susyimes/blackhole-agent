# Skill Route Discovery Pass 3 Proposal Replay Plan

## Hypothesis

The active skill-route-discovery pass needs an operator-visible replay plan keyed by proposal id, not only a route-level readiness status. The plan should convert the current evidence into bounded local validation lanes before activation:

- `proposal-skill-route-discovery-zhengxi-views` -> skill-route discovery classification lane.
- `proposal-codex-skill-workflow-gate` -> skill-route-discovery-first Codex workflow gate.
- `proposal-agent-harness-qwen-agentworld` -> agent-harness-eval-required lane before any implementation route.

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: repository exposes `SKILL.md`, `skill.yml`, `evals`, `references`, and source-cited workflow/advice-boundary language.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: repository presents an AI Agent / Codex local workflow skill, which supports keeping Codex workflow handling behind a local skill-route-first gate.
- `https://github.com/QwenLM/Qwen-AgentWorld`: repository is a general-agent benchmark/project signal, not a local skill package, so it remains behind agent harness evaluation.

Only the proposal URLs were reviewed; no broad trend discovery was rerun.

## Change

- Added `proposal_replay_plan` to `current_pass3_skill_route_replay_lane`.
- Updated the active pass-3 proposal ids to match this run's anchoring proposals.
- Added regression coverage that asserts the replay plan is body-free, non-executing, and keeps Qwen-AgentWorld behind `agent_harness_eval_required`.
- Documented the new pass-3 replay-plan contract in `docs/architecture.md`.

## Rollback

- Rollback ref: `refs/blackhole-agent/rollback/20260704T045307Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260704T045307Z-skill-route-discovery-pass3/rollback-point.md`

## Validation

```powershell
python -m pytest tests/test_proposal_eval.py -q -k current_pass3_skill_route_replay_lane
python -m pytest tests/test_proposal_eval.py tests/test_github_growth.py -q -k "current_pass3_route_readiness_index or current_pass3_operator_gate"
python -m pytest tests/test_proposal_eval.py tests/test_github_growth.py -q -k "current_pass3_skill_route_replay_lane or current_pass3_route_readiness_index or current_pass3_operator_gate"
python -m pytest tests/test_docs_contracts.py -q
```

All validation passed.

## Review Notes

- No self-model edit was made. The existing preference for rollback-backed local evolution matched this run and did not need new structure.
- No external skill code was installed, cloned, or executed.
- Raw source URLs and raw replay commands remain denied in the controller surface; tests assert these strings are absent from the serialized replay lane.
