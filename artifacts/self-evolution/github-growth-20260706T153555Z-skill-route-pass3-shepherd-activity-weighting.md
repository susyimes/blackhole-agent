# Skill Route Discovery Pass 3: Shepherd Activity Weighting

- Source digest: `github-growth-20260706T153555.720534Z`
- Capability window: `skill-route-discovery`, pass 3 of 4
- Selected proposal: `p5-shepherd-activity-dedup-and-weighting`
- Rollback artifact: `artifacts/rollback/20260706T153554Z-skill-route-discovery-pass3-shepherd-activity-weighting/rollback-point.md`
- Rollback ref: `refs/rollback/20260706T153554Z-skill-route-discovery-pass3-shepherd-activity-weighting`

## Evidence

- `https://github.com/shepherd-agents/shepherd/issues/23` reports a provider lane failure with `ProviderInvocationError`, an empty envelope, a green doctor preflight, and a recovery question about actionable diagnostics.
- `https://github.com/shepherd-agents/shepherd/pull/26` is direct recovery work for interrupted runs, run-start auto-recovery, and manual repair.
- Generic or untitled Shepherd PR/push activity is useful freshness pressure, but it is weaker than issue/PR evidence that names a route failure, provider diagnostic, or recovery workflow.

## Hypothesis

Context-budget ranking should let direct-detail provider failure and recovery evidence survive before repeated generic PR/push movement. The rule must not weaken existing `skill_workflow` trend/fork/push pressure, because that pressure is the active route-discovery slice.

## Change

- Added generic push clustering and duplicate confidence penalties beside the existing generic PR cluster handling.
- Removed direct priority from any generic or untitled PR, even when it is not repeated.
- Added direct-detail priority for issue/comment evidence that names route failure, provider diagnostic, empty-envelope, doctor/preflight, or recovery/repair details.
- Preserved direct priority for classified `skill_workflow` pushes so repeated skill-route activity still ranks as bounded local route pressure.
- Updated frozen proposal replay expectations where generic PR metadata now sorts after direct trend/review detail.

## Validation

- `python -m pytest tests/test_github_growth.py -q` passed: 102 passed.
- `python -m pytest tests/test_proposal_eval.py -q` passed: 31 passed.

## Self-Model

Read `docs/self-model.md` before choosing the patch. It already matches this run's narrow safety boundary and preference for locally validated behavior changes, so it was left unchanged.

## Review Notes

- This is a ranking and evidence-budget change only. It does not grant runtime action, provider launch, external harness execution, remote execution, push, promotion, or restart authority.
- The shepherd evidence was reviewed only through the provided proposal URLs; no broad trend discovery was rerun.
