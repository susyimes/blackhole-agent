# Run notes

Digest: github-growth-20260713T033123.572996Z
Branch: grok/blackhole-evolve/20260713T033151.775031-advance-reverse-flow-skill-route-discovery-via-b
Rollback: refs/blackhole-rollback/20260713T113313Z

## Hypothesis

Residual stage packets already held selected_residual_proposal_id while reverse-flow-waiting, but reverse-flow focused validation, activation-external handoff/acceptance, residual queue, and residual apply still pre-exported fortress adjacent_general_agent_proposal_ids and residual_adjacent_harness_eval_available=true. That could lure operators past reverse-flow record/close.

## Change

Hold residual adjacent ID/availability exports on reverse-flow-waiting surfaces until residual-active readiness (recorded pass / ready handoff / accepted / residual queue ready).

## Validation

pytest tests/test_github_growth.py -q -k skill_route_discovery -> 17 passed
pytest tests/test_docs_contracts.py -q -k skill_route -> 24 passed

## Actions

- Created rollback ref refs/blackhole-rollback/20260713T113313Z
- Edited src/blackhole_agent/github_growth.py
- Edited tests/test_github_growth.py
- Edited docs/skill-route-discovery.md
- Edited docs/self-model.md
