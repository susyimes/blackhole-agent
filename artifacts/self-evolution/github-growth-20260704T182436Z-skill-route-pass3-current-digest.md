# Skill Route Discovery Pass 3 Current Digest

- Source digest: `github-growth-20260704T182436.018333Z`
- Theme: `skill-route-discovery`
- Capability pass: `3 of 4`
- Rollback point: `artifacts/rollback/20260704T182436Z-skill-route-discovery-pass3-current-digest/rollback-point.md`
- Rollback ref: `refs/rollback/20260704T182436Z-skill-route-discovery-pass3-current-digest`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow repository with `skills/reverse-flow`, `SKILL.md`, local sandbox / CTF framing, install examples, scripts, and runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with `SKILL.md`, `skill.yml`, references, evals, scripts, source-cited research workflow language, WorkBuddy / MCP automation notes, and an advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent model and benchmark repository with eval / prompt assets but no skill workflow route hint.

## Hypothesis

Current pass-3 skill and route evidence should be promoted to an operator-visible validation and acceptance lane, not to runtime behavior. Codex-oriented skill workflow evidence must prove `skill_route_discovery_first`; generic skill workflow evidence remains documentation/config/test/code_patch only until validation succeeds; general-agent projects stay in `agent_harness_eval_required`.

## Changes

- Specialized `current_run_pass3_validation_lane` for this digest's proposal IDs.
- Added explicit `codex_workflow_gate` visibility and `skill_route_discovery_first` proof on the current-run Codex row.
- Replaced the stale current-run pass-3 fixture with reverse-flow, zhengxi-views, and Qwen-AgentWorld evidence.
- Updated pass-3 validation and acceptance tests for the current proposal set.
- Added a current-digest operator note to `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_run_pass3` passed.
- `python -m pytest tests/test_skill_routing.py -q -k "current_run_pass3 or 20260704T180435 or 20260704T170435"` passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.

## Review Notes

- Runtime action remains `none`.
- External skill activation, external agent activation, external harness execution, provider launch, profile writes, memory writes, and remote execution remain denied.
- Raw source URLs, replay commands, target paths, evidence URLs, and upstream bodies remain excluded from operator lane payloads.
- Self-model was left unchanged because it already describes the current validated-local-evolution posture and did not need a behavior-shaping update for this run.
