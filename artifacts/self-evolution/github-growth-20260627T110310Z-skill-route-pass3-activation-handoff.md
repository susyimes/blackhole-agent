# Skill Route Discovery Pass 3 Activation Handoff

Source digest: `github-growth-20260627T110310.772544Z`

Rollback artifact: `artifacts/rollback/20260627T110309Z-skill-route-discovery-pass3.txt`

## Evidence Reviewed

- `https://github.com/lyra81604/zhengxi-views`: public agent skill evidence with `SKILL.md`, references, evals, scripts, and explicit advisory boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills`: skills directory, helper scripts, install commands, and Three.js browser-game workflow claims.
- `https://github.com/dongshuyan/compass-skills`: skills directory, `skills.sh.json`, task memory, session handoff, and collaboration-profile skill claims.

Only repository-level metadata and README-level evidence were reviewed. No upstream code, skill body, install command, scaffold, dataset, provider, external harness, profile state, or memory state was imported or executed.

## Hypothesis

The active pass needed an operator-visible pre-activation handoff rather than another isolated fixture. A local `pass3_activation_handoff` packet can convert current skill-route validation cases into a replayable supervisor surface while preserving the bounded local lanes: documentation, config, test, and code_patch.

## Change

- Added `pass3_activation_handoff` to the skill-route lane map.
- Bound the current proposal IDs to selected local lanes, validation gates, validation targets, replay commands, source hashes, and activation blockers.
- Added ready and blocked regression coverage for the handoff.
- Updated `docs/skill-route-discovery.md` with the new pass-3 surface.

## Validation Plan

- `python -m pytest tests/test_skill_routing.py -q -k "current_window_pass1_proposal_intake or current_pass_validation_cases"`
- `python -m pytest tests/test_docs_contracts.py tests/test_skill_routing.py -q -k skill_route_discovery`

## Review Notes

- `pass3_activation_handoff` does not activate, install, execute, or enable upstream skills.
- External skill activation, external harness execution, provider launch, remote execution, profile writes, memory writes, raw source URL export, raw evidence URL export, raw target path export, and upstream body export remain denied.
- The self-model was left unchanged because its current preference already supports rollback-backed local behavior improvements with narrow safety boundaries.
