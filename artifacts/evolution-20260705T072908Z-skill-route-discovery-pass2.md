# Skill Route Discovery Pass 2

Source digest: `github-growth-20260705T072819.148283Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/agent skill workflow evidence with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, scripts, install examples, and runtime pressure.
- `https://github.com/Ovlvllo/reverse-flow-skill`: reverse-flow fork-lineage evidence, used as corroborating route pressure rather than a second activation route.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava`: general agent-project evidence without skill workflow route hints or local harness evaluation results.

## Hypothesis

Pass-2 skill-route discovery should expose a bounded local validation lane for reverse-flow skill/workflow signals while keeping adjacent general-agent projects behind `agent_harness_eval_required`. Route hints should shape only documentation, config, test, or code_patch lanes; runtime permission and final implementation scope remain controller-recomputed after local validation.

## Change

- Added `current_digest_20260705T072819_pass2_local_validation_lane.json` as a frozen replay fixture.
- Added a current-digest pass-2 lane builder for `github-growth-20260705T072819.148283Z`.
- Added a regression test for reverse-flow lineage collapse, bounded local lane mapping, and general-agent harness gating.
- Updated `docs/skill-route-discovery.md` with the current pass-2 interpretation.

## Rollback

Rollback point: `artifacts/rollback/20260705T072908Z-skill-route-discovery-pass2/`

Original branch: `codex/blackhole-evolve/20260705T072908.713671-run-a-bounded-local-skill-route-discovery-evalua`

Original HEAD: `92e7e2fe7e6fba4d326311cf97e7adc2f2927dc3`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260705T072819`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 289 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 2 tests.

## Review Notes

- No external repositories were cloned or executed.
- Raw evidence URLs and replay commands remain omitted from the lane output.
- Self-model was read and left unchanged because it already states that local evolution is allowed only when rollback-backed, validated, and bounded by runtime policy.
