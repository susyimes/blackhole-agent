# Evolution: skill-route adjacent fortress harness-eval handoff

Digest: github-growth-20260712T201308.719394Z
Branch: grok/blackhole-evolve/20260712T201402.254450-run-a-bounded-agent-harness-eval-local-compariso
Rollback ref: refs/rollback/blackhole-agent/20260713T041547Z-skill-route-adjacent-fortress-handoff

## Hypothesis

When reverse-flow skill-route candidates are absent and the selected residual
row is fortress-style `agent_harness_eval_required`
(`prop-harness-fortress-local-eval`), the skill-route pipeline was incorrectly
failing local comparison and demanding reverse-flow repair. The correct residual
path is a body-free handoff to `agent_harness_eval_cluster_local_apply`.

## Change

- Adjacent general-agent selections no longer fail
  `skill_route_discovery_local_comparison`; status is `not_applicable`
- Config gates stay ready when isolation holds for adjacent selections
- Local apply / completion become `deferred_adjacent_harness_eval` with
  supervisor action
  `run_agent_harness_eval_local_comparison_for_selected_general_agent_row`
- New surface `skill_route_discovery_adjacent_harness_eval_handoff`
- Hy3 / fortress / agent_harness_eval markers classify as
  `agent_harness_eval_required`
- `prop-harness-fortress-local-eval` selects fortress cluster row and unlocks
  documentation/test/code_patch after criteria pass

## Self-model

Rewrote Skill Route Discovery Habit to record the adjacent handoff repair and
stop treating fortress residual rows as reverse-flow theme failures.

## Validation

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_harness_eval.py tests/test_docs_contracts.py -q -k "skill_route_discovery_capability_pipeline or skill_route_discovery_adjacent_fortress or fortress_from_proposal_token or skill_route_discovery_doc_records_capability_pipeline or architecture_links_upstream"
```

Result: 10 passed.

Broader regression:

```
PYTHONPATH=src python -m pytest tests/test_github_growth.py tests/test_harness_eval.py -q -k "skill_route_discovery or agent_harness_eval_cluster"
```

Result: 176 passed.

## Review notes

- Agent-chief remains privacy review-only; no local apply unlock
- Hy3 remains adjacent harness-eval; not selected when fortress is primary residual
- External skill execution, provider launch, remote apply, push, promotion,
  restart remain denied
- Supervisor owns activation of unlocked documentation/test/code_patch after
  fortress local comparison
