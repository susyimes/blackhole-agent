# Skill Route Discovery Pass 1 Bounded Local Lanes

Source digest: `github-growth-20260629T211904.277568Z`

## Hypothesis

COMPASS and zhengxi-style public skill evidence can be converted into bounded local lanes without fetching upstream
repository content. General agent projects should remain adjacent `agent_harness_eval_required` rows until a local
harness evaluation exists.

## Evidence Interpretation

- `https://github.com/dongshuyan/compass-skills`: skill ecosystem and state handoff signal; local lane remains test,
  documentation, config, or code_patch only.
- `https://github.com/lyra81604/zhengxi-views`: generic skill workflow signal; local lane remains bounded and
  validation-required.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/ksimback/looper`: general-agent project
  evidence; no skill-route inheritance, no direct runtime route, and no external harness execution.
- AutoCVE-style security-agent evidence is treated as review-only context for this pass and does not influence the
  skill-route or general-agent lane.

## Changes

- Added a current digest pass-1 branch to `skill_route_discovery_current_digest_pass1_validation_lane` for
  `github-growth-20260629T211904.277568Z`.
- Exported `current_digest_pass1_validation_lane` from the local harness evaluator output for operator-visible replay.
- Added a frozen local harness fixture and focused tests for the current digest.

## Rollback

Rollback point: `artifacts/rollback/20260629T211903Z-skill-route-discovery-pass1-bounded-lanes.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_digest_20260629T211904`
- `python -m pytest tests/test_harness_eval.py -q -k current_digest_20260629T211904`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery`

All validation commands passed.
