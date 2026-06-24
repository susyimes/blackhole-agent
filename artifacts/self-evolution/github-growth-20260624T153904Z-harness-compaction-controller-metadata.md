# Harness Compaction Controller Metadata

Source digest: `github-growth-20260624T153904.842598Z`
Capability window: `skill-route-discovery`, pass 1 of 4
Rollback artifact: `artifacts/rollback/20260624T154040Z-harness-compaction-skill-route-lane.md`
Rollback ref: `rollback/20260624T154040Z-harness-compaction-skill-route-lane`

## Evidence Read

- `https://github.com/omnigent-ai/omnigent`: public agent framework/meta-harness evidence for multi-harness orchestration, session continuity, policy, and sandboxing.
- `https://github.com/omnigent-ai/omnigent/pull/1131`: reviewed as provider/config preflight evidence, kept review-only because active-session provider mutation can cross privacy/config boundaries.
- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state-handoff evidence for bounded skill-route lanes.
- `https://github.com/lyra81604/zhengxi-views`: source-cited domain skill evidence; treated as a bounded local route-profile signal only.

## Hypothesis

Harness-owned compaction is not complete unless the compacted handoff preserves controller recovery metadata. A local fixture should prove the expected harness compaction path, persistence ordering, replay readiness, and metadata preservation before any supervisor treats compacted context as activation-ready.

## Change

- Added a body-free controller metadata contract to `agent_workflow_route` compaction.
- Required source digest, controller branch, controller HEAD, rollback ref, and recovery command presence when compaction is required.
- Exported only stable hashes, counts, field names, and failure classes; raw refs, recovery commands, summaries, and context bodies remain omitted.
- Added regression coverage for the passing path and the missing-metadata block.

## Validation

- `pytest tests/test_harness_eval.py -q -k "harness_owned_compaction or agent_workflow_route_harness_owned_compaction"`: passed.
- `pytest tests/test_harness_eval.py -q -k "agent_workflow_route"`: passed.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane"`: passed.
- `pytest tests/test_harness_eval.py -q`: passed.
- `ruff check .`: passed.
- `pytest -q`: passed.

## Review Notes

- Self-model left unchanged: it already states the rollback-backed, locally validated behavior preference used here, and this run produced no evidence that the file is shaping behavior incorrectly.
- The MCP add/remove provider-config preflight proposal remains review-only for privacy/config reasons.
- No restart, push, provider launch, external skill activation, or remote execution was performed.
