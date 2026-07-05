# Skill Route Discovery Pass 4

- Source digest: `github-growth-20260705T080817.787301Z`
- Theme: `skill-route-discovery`
- Hypothesis: reverse-flow-style skill workflow evidence should close the four-pass slice through an operator-visible completion handoff that selects only bounded local lanes, while general agent projects stay in `agent_harness_eval_required` until local harness evaluation.
- Rollback ref: `refs/rollback/20260705T080816Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260705T080816Z-skill-route-discovery-pass4/rollback-point.md`

Evidence reviewed:

- `lingbol088-spec/reverse-flow-skill`: public Codex / AI Agent skill workflow with `skills/reverse-flow`, local sandbox/CTF framing, install examples, and scripts. Treated as route evidence only.
- `InternScience/Agents-A1`, `QwenLM/Qwen-AgentWorld`, and `TianhangZhuzth/Fundamental-Ava`: general agent projects without explicit local skill workflow route hints in this digest. Kept as adjacent harness-eval rows.

Changed local surfaces:

- Added `tests/fixtures/skill_route_discovery/current_digest_20260705T080817_pass4_completion.json`.
- Added a digest-specific pass-4 completion handoff in `src/blackhole_agent/skill_routing.py`.
- Added regression coverage in `tests/test_skill_routing.py`.
- Updated `docs/skill-route-discovery.md` with the pass-4 interpretation contract.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260705T080817`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`

Review notes:

- No upstream code, scripts, skill packages, agent projects, harnesses, or providers were installed, launched, or executed.
- The handoff exports proposal IDs, selected item IDs, lane names, route profiles, hashes, and denial booleans only.
- External skill activation, external agent activation, external harness execution, provider runtime launch, remote execution, profile writes, memory writes, raw source URL export, raw replay command export, and upstream body export remain denied.
- The self-model was read and left unchanged because it already describes the current policy preference: rollback-backed local evolution with a narrow safety boundary.
