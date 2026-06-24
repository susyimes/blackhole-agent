# Runner Harness Control Pass 4

## Evidence

- Source digest: `github-growth-20260624T033355.303970Z`
- Capability window: `runner-harness-control`, pass 4 of 4
- Primary upstream lesson: `omnigent-ai/omnigent#1082` moved compaction ownership from runner behavior to harness-owned state and surfaced persistence/resume risks.
- Review-only proposals retained privacy boundaries for provider auth and tracing; no credential, trace body, prompt body, or private context probing was performed.

## Hypothesis

The local runner harness control-plane lane should validate required compaction at the harness boundary. A route should not pass when compaction is merely runner-owned, when raw summaries would be exported, or when live mirror state can advance before persistence and resume replay are recorded.

## Changes

- Added a body-free `agent_workflow_route` compaction contract in `src/blackhole_agent/harness_eval.py`.
- Added a replay fixture for successful harness-owned compaction.
- Added regression coverage for runner-owned compaction and persist-before-mirror split-brain risk.
- Updated aggregate local harness eval counts and privacy serialization assertions.

## Rollback

- Rollback ref: `refs/rollback/20260624T033506Z-runner-harness-control-pass4`
- Rollback artifact: `artifacts/rollback/20260624T033506Z-runner-harness-control-pass4.md`
- Recovery remains explicit and destructive; no rollback commands were executed.

## Validation

- `pytest tests/test_harness_eval.py -q -k "agent_workflow_route_validates_harness_owned_compaction_boundary or local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"`: passed
- `pytest tests/test_harness_eval.py -q`: passed
- `pytest -q`: passed, `411 passed`

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: apply reversible, locally validated behavior changes while keeping privacy-leakage routes review-only.

## Review Notes

- This change does not run external harnesses or provider authentication probes.
- Compaction summaries, event names, artifact paths, rollback refs, and recovery commands remain omitted or hashed in structured output.
- Provider auth preflight and GenAI tracing proposals remain review-only under the privacy-leakage human-review gate.
