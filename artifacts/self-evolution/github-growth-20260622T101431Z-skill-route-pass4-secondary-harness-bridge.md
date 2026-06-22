# Skill Route Discovery Pass 4 Secondary Harness Bridge

Source digest: `github-growth-20260622T101431.744533Z`

Rollback: `artifacts/rollback-20260622T101532-skill-route-discovery.md`

Hypothesis: pass-4 skill-route completion should expose an operator-visible
bridge to the broader `agent_harness_eval_lane` before any general-agent
behavior adoption. The bridge should keep skill-route validation first, keep
secondary harness evaluation blocked until local corroboration, and deny
external harness execution, provider launch, remote execution, and raw upstream
body export.

Evidence used:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/omnigent-ai/omnigent`

Change:

- Added `secondary_harness_bridge` to the pass-4 skill-route completion report.
- Included the bridge in `completion_consistency_guard` status checks.
- Documented the bridge in `docs/skill-route-discovery.md`.
- Extended pass-4 harness tests to assert the bridge contract and denials.

Validation:

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery or agent_harness_eval_lane"` passed.
- `pytest tests/test_skill_routing.py tests/test_proposal_eval.py -q` passed.
- `pytest tests/test_harness_eval.py -q` passed.

Review notes:

- Self-model left unchanged. It already favors rollback-backed, locally
  validated behavior changes and did not need a narrower rewrite for this run.
- No upstream code, install commands, providers, or external harnesses were run.
- The bridge is metadata-only and keeps `agent_harness_eval_lane` blocked until
  a later local fixture maps candidate claims to existing controller invariants.
