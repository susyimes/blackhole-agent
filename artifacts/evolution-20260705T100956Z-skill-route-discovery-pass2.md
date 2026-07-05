# Evolution Run: skill-route-discovery pass 2

- Branch: `codex/blackhole-evolve/20260705T101101.360845-run-a-bounded-skill-route-discovery-validation-f`
- Original HEAD: `88f6243f7a98cfec87f9ac90cf851b1c60f0045e`
- Rollback ref: `refs/rollback/blackhole-agent/20260705T100956Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback-20260705T100956Z-skill-route-discovery-pass2.md`
- Source digest: `github-growth-20260705T100958.062665Z`
- Self-model: read and left unchanged. It already says locally validated, rollback-backed evolution is preferred, and this run had stronger evidence for a route-lane behavior change than for rewriting self-description text.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow skill package with `skills/reverse-flow`, `SKILL.md`, local CTF/sandbox framing, staged reverse-analysis workflow, install examples, and scripts. Interpreted as skill-route evidence only; install, script, runtime, and reverse-workflow pressure remains diagnostic.
- `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/InternScience/Agents-A1`: general agent or benchmark project evidence without explicit skill-route hints or local harness results. Interpreted as adjacent `agent_harness_eval_required` rows.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow-topic repository with Blender/Seedance/MCP/agent-assisted workflow pressure but no local skill-route candidate. Interpreted as a general agent-harness evaluation path input, not a direct workflow adoption path.

## Hypothesis

The active pass-2 slice should produce a replayable local validation lane for the current digest instead of relying on nearby prior fixtures. Reverse-flow skill evidence should map to bounded documentation/config/test/code_patch lanes, while general-agent and workflow-topic trends without route hints must remain behind local harness evaluation with no runtime or code_patch authority before that evaluation.

## Changes

- Added the current digest fixture `tests/fixtures/skill_route_discovery/current_digest_20260705T100958_pass2_local_validation_lane.json`.
- Extended `src/blackhole_agent/skill_routing.py` so `github-growth-20260705T100958.062665Z` uses the specialized pass-2 reverse-flow/general-agent route split with current proposal IDs.
- Added regression coverage in `tests/test_skill_routing.py`.
- Documented the current pass-2 route rule in `docs/skill-route-discovery.md`.

## Validation

- `python -m py_compile src/blackhole_agent/skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k 20260705T100958`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260705T100958 or 20260705T084958"`: passed, 2 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 297 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

## Review Notes

- No external skill, provider, harness, agent, workflow, script, or remote execution was activated.
- The new operator-visible lane exports proposal IDs, route profiles, lane names, selected item IDs, and hashes, but denies raw source URL export, raw evidence URL export, raw replay command export, raw target path export, and upstream body export.
- Workflow-topic evidence without an explicit skill-route signal remains in `agent_harness_eval_required` and cannot open direct runtime or code_patch lanes before local harness evaluation.
