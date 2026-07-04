# Skill Route Discovery Pass 3 Operator Lane

- Source digest: `github-growth-20260704T061309.969283Z`
- Theme: `skill-route-discovery`
- Capability pass: 3 of 4
- Rollback point: `artifacts/rollback/20260704T061307Z-skill-route-discovery-pass3-current-window/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public skill workflow evidence with source-citation and advice-boundary shape.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill evidence with install/runtime pressure that must stay diagnostic.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general-agent benchmark/world-model evidence without a local skill route.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous-agent evidence without a local skill route.

## Hypothesis

The current pass should expose a replayable operator lane rather than another standalone validation report: zhengxi-views and reverse-flow-skill can be converted into bounded local `test` lanes, while Qwen-AgentWorld and Fundamental-Ava remain behind `agent_harness_eval_required` before any implementation lane opens.

## Change

- Added an explicit `github-growth-20260704T061309.969283Z` branch to `current_source_digest_pass3_operator_lane`.
- Added a frozen fixture for the current evidence window.
- Added regression coverage proving:
  - zhengxi-views selects the local test lane through source-cited skill workflow validation;
  - reverse-flow-skill selects the local test lane through Codex workflow-gate validation;
  - Qwen-AgentWorld and Fundamental-Ava stay adjacent and cannot open direct runtime or code_patch routes;
  - raw source URLs, replay commands, upstream bodies, provider runtime, remote execution, and runtime action are not exported.
- Updated `docs/skill-route-discovery.md` with the current pass-3 operator lane contract.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260704T061309 or current_source_digest_pass3_operator_lane"` passed before artifact handoff.
- `python -m pytest tests/test_skill_routing.py -q` passed with 250 tests.
- `python -m ruff check src\blackhole_agent\skill_routing.py tests\test_skill_routing.py` passed.

## Review Notes

- No upstream code was cloned, installed, executed, or activated.
- The self-model was read and left unchanged because it already favors rollback-backed, locally validated route behavior changes over validation-only reports.
