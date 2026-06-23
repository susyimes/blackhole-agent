# Runner Harness Control Plane Pass 2

- Source digest: `github-growth-20260623T163348.965512Z`
- Capability window: `runner-harness-control`, pass 2 of 4
- Rollback ref: `refs/blackhole-rollback/20260624T003348Z-runner-harness-control-pass2`
- Rollback artifact: `artifacts/rollback/20260624T003348Z-runner-harness-control-pass2.md`

## Evidence Summary

Reviewed the carried public evidence only:

- `https://github.com/baskduf/FableCodex` presents Codex workflow gates, review ledgers, and verification habits.
- `https://github.com/dongshuyan/compass-skills` presents local skill ecosystem state, task memory, handoff, profile, and validation notes.
- `https://github.com/lyra81604/zhengxi-views` presents a source-cited domain skill with explicit advice boundaries.
- `https://github.com/majidmanzarpour/threejs-game-skills` presents a director/specialist game workflow with QA, browser checks, and asset/provider boundaries.
- `https://github.com/omnigent-ai/omnigent` presents a public meta-harness framing around multiple agent harnesses, policies, and sandboxing.

Reusable lesson: runner-control evidence is more useful when the operator can trace the route from source intake through mid-flight state, recovery, replay, and report artifacts without exposing upstream URLs, prompts, command bodies, or local paths.

## Hypothesis

The pass-1 control-plane checklist made missing report and recovery steps visible, but it did not record a body-free intake contract tied to the source digest/proposals that justified the run. Adding source-aware stage diagnostics makes the workflow more replayable and gives later supervisor surfaces a compact contract to display.

## Change

Extended `agent_workflow_route` evaluation with:

- Optional `intake` metadata for source digest, proposal IDs, evidence URLs, and capability-window pass/profile metadata.
- `control_plane.intake`, which exports counts and stable hashes while omitting raw URLs and proposal bodies.
- `control_plane.stage_diagnostics`, which reports each stage's readiness, reason, action, and evidence counts.
- Checklist stage failure reasons, so blocked routes show why a stage must be repaired before replay.
- A pass-2 fixture that exercises intake, mid-flight state, recovery handoff, replay artifact, and report artifact in one route.

## Validation

- `pytest tests/test_harness_eval.py -q -k agent_workflow_route`
- `pytest tests/test_harness_eval.py -q`

Both passed.

## Review Notes

- No upstream code, skills, install scripts, providers, browser checks, or remote harnesses were executed.
- The self-model was read and left unchanged because the current preference already supports rollback-backed, locally validated behavior improvements.
- Remaining uncertainty: this improves the local evaluator and replay fixture surface. A later pass can thread `stage_diagnostics` into an external supervisor/operator report if that surface exists.
