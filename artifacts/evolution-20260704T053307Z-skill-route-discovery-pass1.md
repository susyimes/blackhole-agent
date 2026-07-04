# Evolution Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260704T053309.188012Z`
- Branch: `codex/blackhole-evolve/20260704T053614.616155-add-or-extend-a-bounded-local-skill-route-discov`
- Rollback ref: `refs/blackhole/rollback/20260704T053307Z`
- Rollback artifact: `artifacts/rollback-20260704T053307Z-skill-route-discovery-pass1.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill repository with `skills/reverse-flow/SKILL.md`, scripts, local sandbox/CTF framing, and upstream install/runtime examples that must stay diagnostic-only locally.
- `https://github.com/lyra81604/zhengxi-views`: generic/source-cited Agent Skill repository shape suitable for documentation-lane handling.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/world-model project without a skill workflow route hint in this digest.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent project without a skill workflow route hint in this digest.

## Hypothesis

The current digest should expose a replayable pass-1 skill-route lane for the active proposal IDs. Codex-style skill workflow evidence can enter only documentation, config, test, or code_patch lanes after local validation, while general-agent projects without skill workflow hints remain behind `agent_harness_eval_required`.

## Local Change

- Added a `github-growth-20260704T053309.188012Z` branch to `current_digest_pass1_validation_lane`.
- Added a frozen fixture and regression test for the active `p1`, `p2`, and adjacent `p3` handling.
- Documented the pass-1 lane and the evidence item ID citation rule.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T053309`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 248 tests.

## Review Notes

- No upstream code was cloned, installed, imported, or executed.
- Raw evidence URLs, raw upstream bodies, and raw replay commands remain excluded from the controller lane output.
- Qwen-AgentWorld and Fundamental-Ava remain adjacent `agent_harness_eval_required` rows before any local documentation, test, or code_patch adoption lane is eligible.
- The self-model was read and left unchanged because it already permits rollback-backed, locally validated behavior changes and this run produced a direct controller/test/doc improvement.
