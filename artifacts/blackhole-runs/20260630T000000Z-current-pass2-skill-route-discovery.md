# Current Pass 2 Skill Route Discovery

Source digest: `github-growth-20260629T201904.282006Z`

Hypothesis: COMPASS-style skill ecosystem evidence and zhengxi-views-style
generic skill workflow evidence should advance through bounded local lanes,
while Qwen-AgentWorld and looper remain adjacent general-agent projects behind
`agent_harness_eval_required`.

Rollback:
- Ref: `refs/blackhole-agent/rollback/20260630T000000Z-current-pass2-skill-route-discovery`
- Artifact: `artifacts/rollback-20260630T000000Z-current-pass2-skill-route-discovery.md`

Changed surfaces:
- Added fixture `current_digest_20260629T201904_pass2_skill_ecosystem_handoff.json`.
- Specialized `current_digest_pass2_local_validation_lane` for the current
  source digest and proposal IDs.
- Added `skill_ecosystem_handoff_path` as an operator-visible pass-2 handoff
  surface.
- Updated `docs/skill-route-discovery.md` with the pass-2 interpretation.

Validation:
- `pytest tests/test_skill_routing.py -q -k "201904_pass2 or 195904_pass1"` passed.
- `pytest tests/test_skill_routing.py -q` passed.
- `pytest tests/test_docs_contracts.py -q` passed.

Review notes:
- No upstream skill installation, execution, provider launch, profile write,
  memory write, external harness execution, remote execution, or raw upstream
  body export was added.
- Self-model was read and left unchanged; it already matches the active policy
  for rollback-backed, locally validated route behavior.
