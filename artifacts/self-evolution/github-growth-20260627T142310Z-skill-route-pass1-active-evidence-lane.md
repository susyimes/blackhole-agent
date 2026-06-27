# Skill Route Discovery Pass 1 Active Evidence Lane

Source digest: `github-growth-20260627T142310.634775Z`

Rollback point:
`artifacts/rollback/20260627T142425Z-skill-route-discovery-pass1.txt`

Rollback ref:
`refs/rollback/20260627T142425Z-skill-route-discovery-pass1`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/QwenLM/Qwen-AgentWorld`

Reusable lesson:
skill workflow repositories can become bounded local validation lanes, but
general-agent projects without skill workflow signals must remain behind
`agent_harness_eval_required` rather than inheriting `skill_route_discovery` or
becoming direct runtime/code_patch routes.

## Change

- Added body-free `ignored_evidence_items` metadata to evidence-item registry
  builds so ignored general-agent evidence is visible to operators without raw
  source URL export.
- Added `active_pass1_evidence_lane` to the skill-route proposal lane map.
- Added a frozen current-window fixture covering COMPASS Skills, zhengxi-views,
  Three.js Game Skills, and Qwen-AgentWorld.
- Added regression coverage asserting accepted skill-route candidates stay in
  documentation/config/test/code_patch lanes with `local_validation_required:
  true`, while Qwen-AgentWorld is queued for agent-harness evaluation with no
  direct runtime or code_patch route.
- Updated `docs/skill-route-discovery.md` with the active pass-1 interpretation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k active_pass1_fixtures`
  - Result: passed, `1 passed, 44 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: passed, `45 passed`
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: passed, `11 passed`
- `python -m pytest -q`
  - Result: passed, `440 passed`

## Review Notes

- Self-model was read and left unchanged. It already matched the run policy:
  prefer rollback-backed local behavior changes when validation can cover them.
- No upstream code, prompts, install scripts, datasets, or skill bodies were
  imported.
- Raw source URLs are present only in the fixture and docs as evidence context;
  emitted operator rows use hashes and selected IDs.
- The new lane is an operator-visible validation surface only. It does not
  grant runtime action, external skill or agent activation, external harness
  execution, provider launch, remote execution, profile writes, memory writes,
  raw target path export, or upstream body export.
