# Skill Route Discovery Pass 3 Activation Review

- Source digest: `github-growth-20260629T215904.320352Z`
- Branch: `codex/blackhole-evolve/20260629T215944.136747-add-or-extend-local-route-discovery-regression-c`
- Rollback artifact: `artifacts/rollback/20260630T000000Z-skill-route-discovery-pass3-current-window.md`
- Rollback ref: `refs/rollback/skill-route-discovery-pass3-current-window-20260630T000000Z`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

The reusable lesson is that public skill and agent repositories should enter a
bounded local activation-review lane before pass 4. COMPASS-style state handoff
and zhengxi-views-style agent plus skill workflow evidence remain limited to
documentation, config, test, or code_patch lanes with local validation required.
Qwen-AgentWorld and looper remain adjacent general-agent projects that require
agent_harness_eval before documentation, test, or code_patch work is proposed.

## Local Changes

- Added `current_digest_pass3_activation_review_lane` to the skill-route lane map.
- Added a frozen current-digest fixture for COMPASS, zhengxi-views, Qwen-AgentWorld, and looper.
- Added regression coverage for the pass-3 review lane, bounded lanes, denied runtime actions, and adjacent general-agent eval.
- Documented the pass-3 lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260629T215904 or 20260629T213904_pass2_operator_lane"`: passed
- `python -m pytest tests/test_skill_routing.py -q`: passed
- `python -m pytest tests/test_docs_contracts.py -q`: passed

## Review Notes

- No runtime action, external skill activation, external harness execution,
  provider launch, profile write, memory write, remote execution, raw URL export,
  replay-command export, target-path export, or upstream body export was added.
- The self-model was read and left unchanged because the run produced a direct,
  rollback-backed behavior improvement consistent with its current preference.
