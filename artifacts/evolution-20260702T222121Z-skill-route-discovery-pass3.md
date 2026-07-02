# Evolution Run: Skill Route Discovery Pass 3

- Source digest: `github-growth-20260702T222121.903294Z`
- Branch: `codex/blackhole-evolve/20260702T222213.746437-add-a-bounded-local-validation-lane-for-skill-wo`
- Rollback artifact: `artifacts/rollback-20260702T222121Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260702T222121Z`

## Evidence

The current window carries zhengxi-views as explicit skill-route evidence and
Qwen-AgentWorld, Fundamental-Ava, looper, and Seedance workflow-usecase evidence
as adjacent agent/workflow routing pressure. The reusable lesson is that
workflow and general-agent trend signals must remain in bounded local lanes
until local harness evaluation separates implementation-ready claims from
repository-level popularity.

## Hypothesis

Making the current pass-3 activation review lane digest-specific will improve
operator visibility: zhengxi-views should map to a bounded local test lane,
general-agent projects should remain under `agent_harness_eval_required`, and
workflow-only Seedance evidence should be documentation triage behind the same
harness boundary.

## Changes

- Added `github-growth-20260702T222121.903294Z` handling to
  `current_digest_pass3_activation_review_lane`.
- Added a workflow-only evidence classifier so the active pass separates
  Seedance workflow-usecase evidence from the aggregate general-agent harness
  row.
- Added a regression covering the active digest and proposal IDs.
- Documented the current pass-3 route split in `docs/skill-route-discovery.md`.

The self-model was read and left unchanged because this run produced a concrete
behavioral routing improvement; the self-model remains descriptive context, not
an executable route source.

## Validation

- `PYTHONPATH=src pytest tests/test_skill_routing.py -q -k 20260702T222121`
- `PYTHONPATH=src pytest tests/test_skill_routing.py -q`
- `PYTHONPATH=src python -m py_compile src/blackhole_agent/skill_routing.py`
- `PYTHONPATH=src pytest tests/test_docs_contracts.py -q`
- `PYTHONPATH=src pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`

All validation commands passed.

## Review Notes

- No runtime action, external skill activation, provider launch, external
  harness execution, remote execution, raw upstream body export, raw source URL
  export, replay-command export, or target-path export was enabled.
- The workflow-only classifier is intentionally conservative and scoped to
  digest metadata. It is used only to keep the active pass-3 general-agent row
  from absorbing workflow-usecase evidence that has no skill-route hint.
