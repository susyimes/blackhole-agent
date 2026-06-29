# Run Notes: skill-route-discovery pass 1

- Source digest: `github-growth-20260629T223904.363629Z`
- Capability window: `skill-route-discovery`, pass 1 of 4
- Rollback artifact: `artifacts/rollback/20260629T223903Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/blackhole-agent/rollback/20260629T223903Z-skill-route-discovery-pass1`

## Evidence Interpretation

Focused evidence review used the carried proposal URLs:

- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/ksimback/looper`

Reusable lesson: skill and route evidence should become bounded local validation
lanes before activation. COMPASS-style skill ecosystem handoff evidence maps to
local tests. zhengxi-style generic skill workflow evidence maps to local
documentation. Qwen-AgentWorld and looper stay adjacent under
`agent_harness_eval_required`; they do not inherit `skill_route_discovery` or
direct runtime, provider, harness, or code patch authority. The security-agent
anchor remains review-only at the offensive-behavior boundary.

## Local Changes

- Added source-digest-aware pass-1 routing for `github-growth-20260629T223904.363629Z`.
- Added a local harness fixture that replays the current proposal IDs and denial flags.
- Added focused harness regression coverage and updated aggregate fixture counts.
- Documented the operator-visible pass-1 replay surface.

## Validation

```powershell
python -m pytest tests/test_harness_eval.py -q -k "20260629T223904_pass1_validation_lane"
python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass1_validation_lane or 20260629T211904_pass1 or 20260629T195904 or 20260629T171904"
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc
```

All validation commands passed.

## Review Notes

- Self-model was read and left unchanged; it already supports this run's validated local evolution policy and did not need a new behavior-shaping claim.
- No restart, push, promotion, remote execution, provider launch, profile write, memory write, or external harness execution was performed.
