# Skill Route Discovery Pass 4 Agent Harness Eval Lane

- Source digest: `github-growth-20260706T211555.777190Z`
- Rollback ref: `refs/rollback/20260706T211554Z-skill-route-discovery-pass4-agent-harness-eval-lane`
- Rollback artifact: `artifacts/rollback/20260706T211554Z-skill-route-discovery-pass4-agent-harness-eval-lane/rollback-point.md`
- Selected proposal: `p1-agent-harness-eval-shepherd`
- Related proposals: `p2-skill-route-discovery-reverse-flow`, `p3-general-agent-project-comparison-matrix`

## Evidence

Allowed public evidence was reviewed narrowly:

- `https://github.com/shepherd-agents/shepherd` describes an early-alpha agent runtime substrate centered on inspectable, reversible traces, retained outputs, sandboxing, supervision, and review before selection.
- `https://github.com/shepherd-agents/shepherd/pull/29` was available as current Shepherd activity evidence but did not justify direct local runtime adoption.
- `https://github.com/lingbol088-spec/reverse-flow-skill` remains skill/workflow route evidence only; install, run, script, provider, and reverse-workflow pressure stays diagnostic.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava` remain general-agent evidence that requires local harness evaluation before follow-up lanes.

## Hypothesis

Workflow-orchestration ideas from public agent runtimes are useful only when
converted into local, replayable pass/fail criteria before activation. A
controller-visible lane should let the supervisor recompute whether a project
is ready for documentation, test, or code_patch follow-up without running
upstream code or exporting source bodies.

## Change

`agent_harness_eval_lane` now emits `workflow_orchestration_eval_lane`.
The lane records:

- body-free orchestration signals such as reversible trace, fork, replay,
  revert, sandboxing, session supervision, and workflow validation;
- pass/fail criteria for project probe completeness and side-effect denial;
- expected controller recomputation inputs;
- explicit denials for network access, credential access, provider launch,
  external harness execution, remote execution, and unreviewed workspace writes.

The new fixture
`tests/fixtures/local_harness_eval/agent_harness_eval_lane_20260706T211555_workflow_orchestration.json`
exercises Shepherd-style orchestration evidence and reverse-flow workflow route
pressure as local-only metadata.

## Validation

Passed:

`python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or local_harness_eval_runs"`

Result: 8 passed, 238 deselected.

## Review Notes

- No upstream code was cloned, installed, imported, or executed.
- No provider runtime, remote execution, external harness, credential access, or network-dependent validation path was added.
- `docs/self-model.md` was read and left unchanged; its current preference already supports locally validated behavior improvements over more report-only scaffolding.
