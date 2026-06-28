# Skill Route Discovery Pass 1 Active Proposal Aliases

- Source digest: `github-growth-20260628T110729.847216Z`
- Branch: `codex/blackhole-evolve/20260628T110832.888986-add-or-extend-local-validation-coverage-for-gene`
- Rollback ref: `refs/rollback/20260628T110728Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260628T110728Z-skill-route-discovery-pass1.md`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public source-cited agent skill with `SKILL.md`, references, scripts, evals, and advisory boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: public agent skills for Three.js browser game workflows, QA, UI, and optional asset workflows.
- `https://github.com/dongshuyan/compass-skills`: public COMPASS skill ecosystem with state/profile/handoff framing.

## Hypothesis

The active pass carries hyphenated proposal IDs, while the existing local
validation surface used older underscore-style case IDs. Operators should be
able to replay the current digest without manually translating proposal IDs, and
the replay must still keep skill evidence inside documentation, config, test,
or code_patch lanes before activation.

## Change

- Added the active pass proposal IDs as aliases on
  `current_pass_validation_cases`.
- Added a current digest fixture that maps zhengxi-views,
  threejs-game-skills, and COMPASS Skills into bounded skill-route lanes while
  keeping Qwen-AgentWorld adjacent as `agent_harness_eval_required`.
- Added regression coverage for the active digest fixture and updated the
  older alias regression.
- Documented the current digest pass-1 alias behavior.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass1_active_proposals_are_bounded or current_pass1_aliases_match_active_proposals"
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
python -m pytest tests/test_skill_routing.py -q
python -m pytest -q
```

Results:

- `2 passed, 73 deselected in 0.92s`
- `2 passed, 9 deselected in 0.02s`
- `75 passed in 0.25s`
- `481 passed in 7.88s`

## Review Notes

- The self-model was read and left unchanged. It already describes the local
  evolution preference and narrow safety boundary used by this run.
- The validation surface exports proposal IDs, aliases, selected item IDs,
  hashes, bounded lanes, and validation metadata only.
- Runtime action, install, upstream skill activation, external harness
  execution, provider launch, profile writes, memory writes, remote execution,
  raw source URL export, raw evidence URL export, raw target path export, and
  upstream body export remain denied.
