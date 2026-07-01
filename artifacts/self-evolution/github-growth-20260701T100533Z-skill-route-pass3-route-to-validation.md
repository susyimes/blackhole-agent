# Skill Route Discovery Pass 3: Route-To-Validation Lane

- Source digest: `github-growth-20260701T100533.329031Z`
- Capability slice: `skill-route-discovery`
- Pass: 3 of 4
- Rollback ref: `refs/rollback/20260701T180646Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260701T180646Z-skill-route-discovery-pass3.md`

## Hypothesis

The current trend window has one skill-route signal, `zhengxi-views`, and three
general-agent project signals, `Qwen-AgentWorld`, `Fundamental-Ava`, and
`looper`. A pass-3 operator packet should make that split visible before pass-4:
skill-route evidence may enter only documentation, config, test, or code_patch
local validation lanes, while general-agent projects require local
`agent_harness_eval` before any implementation scope is selected.

## Local Change

- Added `current_digest_pass3_route_to_validation_lane` to the skill route
  discovery proposal lane map.
- Added a frozen current-digest fixture covering zhengxi-views, Qwen-AgentWorld,
  Fundamental-Ava, and looper.
- Added a regression test proving the packet exports hashes and denial booleans,
  not raw GitHub URLs or raw replay commands.
- Documented the pass-3 packet in `docs/skill-route-discovery.md`.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k routes_to_validation
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q
```

All validation commands passed in this run.

## Review Notes

- No external repository code was fetched or executed.
- The self-model was read and left unchanged; it already supports rollback-backed
  local validation over validation-report-only work.
- Activation, restart, push, provider launch, external harness execution,
  profile writes, memory writes, raw URL export, and raw replay-command export
  remain denied in the new packet.
