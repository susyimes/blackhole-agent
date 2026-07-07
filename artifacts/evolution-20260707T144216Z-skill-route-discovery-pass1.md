# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260707T144109.514783Z`
- Capability slice: `skill-route-discovery`
- Branch: `codex/blackhole-evolve/20260707T144216.639333-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback ref: `refs/rollback/20260707T144216-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260707T144216Z-skill-route-discovery-pass1-current-window/rollback-point.md`

## Evidence Reviewed

- `https://github.com/Pluviobyte/rnskill`: skill collection with `skills/`, docs, tools, marketplace metadata, and `SKILL.md`-compatible workflow language.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex and AI Agent skill workflow evidence with local sandbox and script/runtime pressure treated as diagnostic only.
- `https://github.com/InternScience/Agents-A1`: general agent project evidence without local skill workflow route metadata.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent evidence without local skill workflow route metadata.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime substrate evidence, kept behind agent harness evaluation before any runtime/controller adoption.

## Hypothesis

Current pass-1 skill and route evidence should become an operator-visible validation lane:
skill repositories may map only to bounded local lanes, while general agent projects must remain adjacent
`agent_harness_eval_required` rows until local harness evaluation exists.

## Changes

- Added the `github-growth-20260707T144109.514783Z` pass-1 route branch to `current_digest_pass1_validation_lane`.
- Added a frozen body-free fixture for `rnskill`, `reverse-flow-skill`, `Agents-A1`, `Fundamental-Ava`, and `shepherd`.
- Added a regression test proving:
  - `rnskill` and `reverse-flow-skill` emit only documentation/config/test/code_patch lanes.
  - `reverse-flow-skill` preserves the `codex_workflow_gate` profile.
  - general agent projects remain `agent_harness_eval_required` with no runtime, provider, external harness, or remote execution allowed.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T144109`
  - Result: `1 passed, 378 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: `379 passed`

## Review Notes

- Self-model was read and left unchanged. It already prefers rollback-backed local validation and was less useful than adding a concrete route behavior path for this pass.
- No external skill activation, install, upstream code execution, provider launch, external harness execution, push, promotion, or restart was performed.
- The `p4_fork_trend_dedup` anchor remains recorded as continuity pressure but was not implemented in this pass because the selected scope was the skill-route validation lane.
