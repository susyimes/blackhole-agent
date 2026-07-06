# Evolution Run: skill-route-discovery pass 3

- Source digest: `github-growth-20260706T022238.766569Z`
- Capability slice: `skill-route-discovery`
- Pass: 3 of 4
- Rollback artifact: `artifacts/rollback/20260706T022237Z-skill-route-discovery-pass3/rollback-point.md`
- Rollback ref: `refs/rollback/20260706T022237Z-skill-route-discovery-pass3`

## Hypothesis

Reverse-flow-skill fork-lineage evidence should strengthen a single bounded
skill-route lane, not create independent activation candidates. General
agent-project trend rows in the same digest should remain adjacent
`agent_harness_eval_required` rows until a bounded local harness evaluation
exists.

## Material Actions

- Added a current-digest pass-3 branch in `src/blackhole_agent/skill_routing.py`.
- Added a frozen pass-3 fixture for the direct reverse-flow item, two fork-lineage
  reverse-flow items, and adjacent Qwen/Agents-A1/Seedance evidence.
- Added a focused regression test that asserts one collapsed reverse-flow lane,
  bounded local lanes only, no runtime authority, and harness-gated adjacent
  agent rows.
- Updated `docs/skill-route-discovery.md` with the operator interpretation for
  `github-growth-20260706T022238.766569Z`.

## Review Notes

- Fork evidence is treated as supporting lineage pressure only.
- The pass exports proposal IDs, item IDs, lane names, hashes, and booleans, not
  raw source URLs, replay commands, upstream bodies, provider inputs, or target
  paths.
- No restart, push, promotion, provider launch, external harness execution,
  external skill activation, remote execution, profile write, or memory write was
  performed.

## Validation

Passed validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T022238
# 1 passed, 314 deselected

python -m pytest tests/test_skill_routing.py -q
# 315 passed
```
