# Skill Route Discovery Pass 3 Claim Remediation

Source digest: `github-growth-20260622T055431.415273Z`

## Hypothesis

The current slice already separates skill/workflow repositories from general
agent projects. FableCodex-style mixed Codex/skill/workflow evidence stays in
`skill_route_discovery_first`, while Omnigent-style general-agent evidence goes
through `agent_harness_eval_required`.

The missing operator-visible behavior was the next step after a general-agent
claim blocks activation as `unmapped_agent_claims`. A blocked lane should say
which local lanes can resolve the unmapped claim before any runtime or upstream
agent behavior is considered.

## Evidence

- `https://github.com/omnigent-ai/omnigent` was reviewed as a public
  meta-harness/general-agent project signal.
- `https://github.com/omnigent-ai/omnigent/pull/924#pullrequestreview-4541429283`
  was treated as upstream movement context, not implementation evidence.
- `https://github.com/baskduf/FableCodex` was reviewed as the carried
  skill/workflow contrast for keeping `skill_route_discovery_first` before a
  broader harness lane.

No upstream code, install commands, skill bodies, or runtime behavior were
imported.

## Change

Added `claim_remediation_plan` to the local `agent_harness_eval_lane` output.
When claims remain unmapped, the plan emits body-free rows with:

- the unmapped claim id;
- recommended local follow-up lanes, currently documentation and test;
- the focused local replay command;
- the `unmapped_agent_claims` activation blocker;
- denied runtime action, external harness execution, provider launch, remote
  execution, external agent activation, and raw claim-body export.

## Files

- `src/blackhole_agent/harness_eval.py`
- `tests/test_harness_eval.py`
- `tests/fixtures/local_harness_eval/agent_harness_eval_lane_general_agent_projects.json`
- `docs/skill-route-discovery.md`
- `artifacts/rollback/20260622T055608-skill-route-discovery-pass3.txt`

Self-model decision: left `docs/self-model.md` unchanged. It already expresses
the relevant preference for rollback-backed, locally validated behavior changes
and did not need another ornamental rewrite for this run.

## Rollback

Rollback ref:
`refs/blackhole-rollback/20260622T055608-skill-route-discovery-pass3`

Recovery commands are recorded in:
`artifacts/rollback/20260622T055608-skill-route-discovery-pass3.txt`

## Validation

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
- `pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures"`
- `pytest tests/test_harness_eval.py -q`
- `python -m compileall -q src tests`

All validation passed.

## Review Notes

The remediation plan is intentionally conservative. It does not map
`local_data_grounding` to a local capability yet; it only makes the blocked
state actionable and replayable for a later pass.
