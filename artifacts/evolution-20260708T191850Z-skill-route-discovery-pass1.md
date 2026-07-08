# Evolution Run: Skill Route Discovery Pass 1

- Source digest: `github-growth-20260708T191850.475615Z`
- Branch: `codex/blackhole-evolve/20260708T191935.921622-create-a-bounded-local-skill-route-discovery-val`
- Rollback ref: `refs/blackhole/rollback/20260708T191850Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260708T191850Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public metadata shows a Codex/AI Agent reverse workflow skill with `skills/reverse-flow`, `SKILL.md`, local sandbox framing, install examples, and scripts.
- `https://github.com/Pluviobyte/rnskill`: public metadata identifies an AI Agent Skills collection.
- `https://github.com/shepherd-agents/shepherd`: public metadata identifies a reversible agent runtime substrate, not a selected local skill route.
- `https://github.com/Tencent-Hunyuan/Hy3`: public metadata identifies a reasoning/agent model project with provider/runtime pressure.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: public metadata identifies workflow-usecase evidence without a selected skill package.

## Hypothesis

The active pass-1 window should expose a bounded local validation lane for reverse-flow and rnskill while keeping Shepherd, Hy3, and Blender/Seedance in `agent_harness_eval_required` until local harness evidence exists.

## Changes

- Added the `github-growth-20260708T191850.475615Z` pass-1 window to skill-route lane classification and activation-readiness routing.
- Added a local harness fixture for the current digest.
- Added direct regression coverage for the current digest.
- Documented the replay surface and activation denials.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: prefer rollback-backed, locally validated behavior changes over ornamental validation reports.

## Validation

Passed:

- `python -m pytest tests/test_harness_eval.py -q -k 20260708T191850`
- `python -m pytest tests/test_harness_eval.py -q -k "20260708T175850 or 20260708T191850 or 20260708T183850"`
- `python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs`

## Review Notes

- No upstream code was installed, cloned, run, or activated.
- External agent, provider runtime, external harness execution, remote execution, promotion, restart, profile writes, and memory writes remain denied by the emitted lane metadata.
