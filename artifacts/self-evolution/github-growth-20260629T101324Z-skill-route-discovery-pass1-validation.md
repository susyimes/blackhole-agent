# Skill Route Discovery Pass 1 Validation

Source digest: `github-growth-20260629T101324.100619Z`

Rollback artifact: `artifacts/rollback/20260629T101324Z-skill-route-discovery-pass1-101324.md`
Rollback ref: `refs/rollback/20260629T101324Z-skill-route-discovery-pass1-101324`

## Evidence Reviewed

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

## Hypothesis

COMPASS-style skill ecosystem evidence and generic skill workflow evidence are
useful route-discovery inputs, but they should become bounded local validation
lanes only. General-agent projects without skill workflow signals should remain
adjacent `agent_harness_eval_required` evidence before any implementation route
is selected.

## Local Change

- Added a current-digest branch for `github-growth-20260629T101324.100619Z` to
  the pass-1 validation lane and current-run activation readiness surface.
- Added a frozen body-free fixture for the active proposal IDs.
- Added a regression test that proves COMPASS maps to the local test lane,
  generic skill workflow evidence maps to documentation, and Qwen-AgentWorld
  plus looper remain adjacent harness-eval rows.
- Updated the skill-route discovery note with the current pass-1 boundary.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260629T101324 or current_digest_pass1_validation_lane or current_run_pass1_activation_readiness"`: passed.

## Review Notes

No offensive-behavior, unauthorized-access, or privacy-leakage route was
implemented. Unsupported `install`, `provider_runtime`, and `runtime_execution`
pressure is retained only as validation pressure and does not appear in allowed
local lanes.
