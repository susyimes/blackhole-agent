# Skill Route Discovery Pass 2 Local Validation Lane

- Source digest: `github-growth-20260628T140729.531143Z`
- Capability slice: `skill-route-discovery`
- Pass: 2 of 4
- Rollback artifact: `artifacts/rollback/20260628T140853Z-skill-route-discovery-pass2-state-handoff.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260628T140853Z`

## Evidence

Carried proposal evidence URLs:

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`

Reusable lesson: skill ecosystem, game/frontend, and generic skill workflow
repositories should be converted into bounded local validation lanes before
activation. Discovery may expose documentation, config, test, and code_patch
work only. Adjacent general-agent harness evidence stays eval-only.

## Hypothesis

An operator-visible current-digest pass-2 lane improves continuity for the
skill-route-discovery window by making the active proposal IDs, route profiles,
selected bounded lanes, required metadata, and replay hashes inspectable without
exporting raw URLs, replay commands, target paths, upstream bodies, or runtime
authority.

## Local Change

- Added `current_digest_pass2_local_validation_lane` to the proposal lane map.
- Added a frozen body-free fixture for the current digest pass-2 evidence.
- Added a regression test that verifies bounded lanes, runtime denial, adjacent
  eval-only handling, and omission of raw GitHub URLs/replay commands.
- Documented the new pass-2 lane in `docs/skill-route-discovery.md`.

Self-model decision: left unchanged. The existing self-model already supports
rollback-backed locally validated behavior changes, and this run did not reveal
a more behavior-shaping revision.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -k current_digest_pass2_local_validation_lane -q
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q
```

Results:

- Focused test: `1 passed, 77 deselected`
- Skill routing module: `78 passed`
- Docs contracts: `11 passed`

## Review Notes

- No upstream code was executed, installed, or imported.
- The packet keeps `runtime_action: none` and denies external skill activation,
  external harness execution, provider launch, remote execution, profile writes,
  and memory writes.
- Evidence-item normalization removes unsupported lane names before this packet
  sees them; the new test therefore asserts the final bounded lane inventory
  rather than downstream downgrade rows.
