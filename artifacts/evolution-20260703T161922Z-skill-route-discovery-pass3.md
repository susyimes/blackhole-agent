# Skill Route Discovery Pass 3

Source digest: `github-growth-20260703T161922.895398Z`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package shape with `skills/reverse-flow/SKILL.md`, local sandbox/CTF framing, scripts, and install/runtime wording. Treated as skill-route evidence only.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill shape with source-cited references, validation/eval paths, and non-investment-advice boundary language. Treated as documentation-lane skill workflow evidence.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent workflow-loop/evaluation project without a skill workflow route hint. Kept behind `agent_harness_eval_required`.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent world-model/evaluation benchmark without a skill workflow route hint. Kept behind `agent_harness_eval_required`.

## Hypothesis

Pass 3 should expose an operator-visible route-to-validation lane for the current digest instead of relying on the previous pass-2 fixture. Reverse-flow skill evidence should validate `skill_route_discovery_first` in the test lane; generic/source-cited skill workflow evidence should remain documentation-first; general agent projects should require local agent-harness evaluation before any implementation lane.

## Rollback

Rollback point: `artifacts/rollback/20260703T161921Z-skill-route-discovery-pass3/rollback-point.json`

## Changed Files

- `src/blackhole_agent/skill_routing.py`
- `tests/fixtures/skill_route_discovery/current_digest_20260703T161922_pass3_operator_lane.json`
- `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260703T161922_pass3_operator_lane.json`
- `tests/test_skill_routing.py`
- `tests/test_harness_eval.py`
- `docs/skill-route-discovery.md`

## Review Notes

- No external repository code was cloned, installed, or executed.
- The new lane exports body-free IDs, hashes, lane names, and denial booleans only.
- Runtime action, external skill or agent activation, provider launch, external harness execution, remote execution, raw URL export, replay-command export, target-path export, and upstream-body export remain denied.
