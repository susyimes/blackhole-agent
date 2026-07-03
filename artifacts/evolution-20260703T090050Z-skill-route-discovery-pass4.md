# Evolution Run: skill-route-discovery pass 4 completion manifest

- Source digest: `github-growth-20260703T090050.734126Z`
- Rollback artifact: `artifacts/rollback-20260703T090050Z-skill-route-discovery-pass4.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T090050Z-skill-route-discovery-pass4`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository presents a Codex / AI Agent skill workflow with a `skills/reverse-flow` layout, local sandbox CTF/crackme framing, scripts, and install pressure. Interpreted only as skill-route evidence; install and runtime pressure remain metadata, not local lanes.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill with source-cited research and advice-boundary framing. Interpreted as generic skill workflow plus source-cited domain profile evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: public general-agent project signals. They remain adjacent `agent_harness_eval_required` evidence and do not inherit skill-route discovery.

## Hypothesis

Final-pass skill-route discovery should have a replayable, operator-visible completion fixture for the active 2026-07-03 digest. The fixture should prove that Codex-oriented skill workflow repositories map only to documentation/config/test/code_patch lanes, while adjacent general-agent projects remain behind agent-harness evaluation.

## Changes

- Added `tests/fixtures/local_harness_eval/skill_route_discovery_current_digest_20260703T090050_pass4_completion.json`.
- Updated `tests/test_harness_eval.py` aggregate fixture counts and added a direct pass-4 manifest regression.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260703T090050_pass4_completion or local_harness_eval_runs_pass_and_fail_fixtures"` passed.
- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane` passed.
- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane` passed.
- `pytest tests/test_harness_eval.py -q -k proposal_interpretation` passed.

## Review Notes

- The self-model was read and left unchanged. Its current preference for rollback-backed local evolution matches this run and did not need a behavior-shaping edit.
- No upstream skill code was installed, imported, executed, or copied. Raw source URLs and replay commands remain non-exported in the structured manifest.
