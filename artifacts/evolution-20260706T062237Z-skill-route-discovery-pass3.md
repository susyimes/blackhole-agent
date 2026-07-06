# Skill Route Discovery Pass 3

Source digest: `github-growth-20260706T062238.861950Z`

Hypothesis: a Codex-style skill/workflow trend should become an operator-visible
local validation lane only after local route discovery, while adjacent general
agent projects remain agent-harness gated until local behavior evidence exists.

Evidence reviewed:

- `https://github.com/lingbol088-spec/reverse-flow-skill` showed a Codex/AI
  Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, references,
  scripts, local sandbox/CTF framing, install examples, and staged workflow
  language.
- `https://github.com/InternScience/Agents-A1`,
  `https://github.com/QwenLM/Qwen-AgentWorld`, and
  `https://github.com/TianhangZhuzth/Fundamental-Ava` were treated as general
  agent project evidence rather than skill-route evidence. The carried Shepherd
  signal stayed in the same general-agent harness-gated class.

Changes:

- Added `github-growth-20260706T062238.861950Z` handling to
  `current_digest_pass3_route_to_validation_lane`.
- Added a frozen current-digest fixture with one reverse-flow skill/workflow
  item and four general-agent items.
- Added a regression test asserting that reverse-flow selects only bounded
  local lanes and that general-agent rows remain `agent_harness_eval_required`
  with no runtime, provider, external harness, remote execution, or direct
  code_patch route before local harness evidence.
- Updated `docs/skill-route-discovery.md` with the current pass-3 route split.

Self-model: left unchanged. The current preference already supports
rollback-backed local experiments while keeping offensive behavior, abuse,
unauthorized access, and privacy leakage outside autonomous apply.

Rollback:

- Ref: `refs/rollback/blackhole-agent/20260706T062237Z`
- Artifact:
  `artifacts/rollback/20260706T062237Z-skill-route-discovery-pass3/rollback-point.md`

Validation:

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k 20260706T062238`:
  passed, 1 test.
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260706T062238 or 20260706T050238 or 20260706T034238"`:
  passed, 3 tests.
- `PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q`:
  passed, 11 tests.
