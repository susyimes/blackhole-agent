# Evolution Run: skill-route-discovery pass 2 local validation

Source digest: `github-growth-20260703T094050.021818Z`
Branch: `codex/blackhole-evolve/20260703T094250.118313-add-or-run-a-bounded-local-skill-route-discovery`
Rollback artifact: `artifacts/rollback/20260703T094050Z-skill-route-discovery-pass2.md`
Rollback ref: `refs/rollback/20260703T094050Z-skill-route-discovery-pass2`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository shape shows Codex/AI Agent skill workflow packaging under `skills/reverse-flow`, local sandbox/CTF framing, and script examples. Interpreted as `codex_workflow_gate` evidence that must pass `skill_route_discovery_first`.
- `https://github.com/lyra81604/zhengxi-views`: public repository shape shows Agent Skill evidence with references, method material, source-citation claims, and an explicit research/non-advice boundary. Interpreted as generic/source-cited skill workflow evidence.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public repository describes a general-agent language world model/benchmark project. Interpreted as adjacent `agent_harness_eval_required`, not skill-route activation.
- `TianhangZhuzth/Fundamental-Ava`: carried by the proposal as adjacent general-agent evidence requiring local harness evaluation before any implementation lane.

## Hypothesis

The active pass-2 slice should expose a replayable local validation lane for Codex and generic skill workflow route discovery, while holding general-agent projects behind agent-harness evaluation. This gives operators a concrete preactivation path without granting runtime permissions or importing upstream skills.

## Changes

- Added current digest handling for `github-growth-20260703T094050.021818Z` in `current_digest_pass2_local_validation_lane`.
- Added a frozen fixture for the active Codex workflow, generic skill workflow, and general-agent harness boundary evidence.
- Added regression coverage for bounded lanes, `skill_route_discovery_first`, controller/supervisor handoff surfaces, and denied runtime/external actions.
- Documented the 09:40 pass-2 lane and replay command in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260703T094050`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260703T094050 or 20260703T054049_pass2 or 20260703T004121 or 20260703T042050"`: passed, 4 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 tests.

## Review Notes

- Self-model was read and left unchanged; its current preference for rollback-backed, locally validated behavior change matches this run.
- No upstream skill code was installed, imported, executed, or activated.
- No provider runtime launch, external harness execution, remote execution, profile write, memory write, push, promotion, restart, raw source URL export, raw evidence URL export, or upstream body export was added.
- Final implementation scope remains controller-recomputed after focused local validation and review.
