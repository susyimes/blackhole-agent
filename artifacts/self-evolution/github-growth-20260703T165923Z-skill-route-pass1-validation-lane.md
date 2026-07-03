# Skill Route Discovery Pass 1 Validation Lane

- Source digest: `github-growth-20260703T165923.653509Z`
- Capability slice: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260703T170019.412583-add-or-run-a-local-skill-route-discovery-validat`
- Rollback artifact: `artifacts/rollback/20260703T165921Z-skill-route-discovery-pass1/rollback-point.json`
- Rollback ref: `refs/blackhole-rollback/20260703T165921Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/reverse-flow`, local sandbox/CTF framing, scripts, and workflow language.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository with skill metadata, references, eval/script framing, and source-cited/non-advice boundary.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent workflow-loop project without a local skill-route signal.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent benchmark/world-model project without a local skill-route signal.

## Hypothesis

Current pass-1 evidence should not fall through the generic route map. It should expose one operator-visible local lane:
reverse-flow-skill enters a bounded `test` lane after `skill_route_discovery_first`; zhengxi-views documents the skill-term
decision rule; adjacent general-agent projects require `agent_harness_eval_required` before any implementation lane.

## Local Change

- Added `github-growth-20260703T165923.653509Z` handling to `current_digest_pass1_validation_lane`.
- Added a frozen current-digest fixture for reverse-flow-skill, zhengxi-views, agent-apprenticeship, Qwen-AgentWorld, and Fundamental-Ava.
- Added regression coverage that verifies bounded lanes, no runtime action, no direct code patch before harness evaluation, and no raw URL/replay-command/runtime-lane export.
- Documented the pass-1 decision rule in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged because its current preference already matches this run and no new behavior-shaping self-description was needed.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T165923` passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.
- `python -m pytest tests/test_skill_routing.py -q` passed.

## Review Notes

- Runtime action, provider launch, external harness execution, remote execution, and external skill/agent activation remain denied.
- General agent project evidence is still preflight-only until a local agent-harness evaluation result exists.
- Activation, promotion, push, restart, and replay remain supervisor-owned.
