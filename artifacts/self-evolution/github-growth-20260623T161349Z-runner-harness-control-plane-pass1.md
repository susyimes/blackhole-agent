# Runner Harness Control Plane Pass 1

- Source digest: `github-growth-20260623T161349.035602Z`
- Capability window: `runner-harness-control`, pass 1 of 4
- Rollback ref: `refs/blackhole-rollback/20260623T161537.727540Z`
- Rollback artifact: `artifacts/rollback/20260623T161537.727540Z.md`

## Evidence Summary

Reviewed the carried public evidence only:

- `https://github.com/baskduf/FableCodex` exposes a Codex workflow package with evidence gates, review ledgers, tests, evals, and verification habits.
- `https://github.com/dongshuyan/compass-skills` exposes a multi-skill local workflow system with clarification, task memory, handoff, local profile, install commands, validation notes, and privacy boundaries.
- `https://github.com/lyra81604/zhengxi-views` exposes a source-cited domain research skill with explicit research-only and advice-boundary language.
- `https://github.com/majidmanzarpour/threejs-game-skills` exposes a runnable skill bundle with install paths, director/specialist orchestration, browser/QA expectations, and asset/provider boundaries.

Reusable lesson: upstream skill or workflow repositories should not become local activation just because they contain useful process. The local controller should surface bounded intake, mid-flight state, recovery, replay, and report actions before replay or promotion.

## Hypothesis

The existing `agent_workflow_route` evaluator already checks the five control-plane stages, but an operator facing an incomplete run had to infer the exact remediation from scattered fields. A body-free replay checklist makes the workflow more legible end to end while preserving privacy and rollback boundaries.

## Change

Added `control_plane.operator_replay_checklist` for `agent_workflow_route` outputs. It reports:

- `ready` when no action is needed.
- `blocked` with stage/action rows when intake, midflight, recovery, replay, or report evidence is incomplete.
- Missing report sections as explicit action codes.
- Hashes for action codes, while keeping raw recovery commands, report bodies, and artifact paths unexported.

Updated the successful control-plane fixture and the missing-report fixture to assert the new operator-visible behavior.

## Validation

- `pytest tests/test_harness_eval.py -q -k agent_workflow_route`
- `pytest tests/test_harness_eval.py -q`

Both passed.

## Review Notes

- No upstream code, skill bodies, install scripts, providers, browser checks, or asset generators were imported or executed.
- The self-model was read and left unchanged because it already matches this run's evidence-backed preference for rollback-backed, locally validated behavior changes.
- Remaining uncertainty: this pass improves the local fixture/control-plane surface, not the external supervisor UI. A later pass can thread the checklist into supervisor-visible run reports if that path is available.
