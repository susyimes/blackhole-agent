# Skill Route Discovery Pass 1

Source digest: `github-growth-20260708T123852.626885Z`
Branch: `codex/blackhole-evolve/20260708T123950.363347-add-a-local-skill-route-discovery-validation-fix`
Rollback point: `artifacts/rollback/20260708T123849Z-skill-route-discovery-pass1/rollback-point.md`

## Hypothesis

The active pass-1 skill-route window should not fall back to generic game/state handoff templates when the digest evidence is a bounded SKILL.md collection plus a Codex workflow skill. It should expose a current-window validation lane for the two skill/workflow repositories and keep workflow/model-agent repositories behind `agent_harness_eval_required`.

## Evidence Reviewed

- `https://github.com/Pluviobyte/rnskill`: SKILL.md collection for Codex, Claude Code, and similar project-level skill workflows.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/local-sandbox skill workflow evidence.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: workflow/use-case collection, not a skill activation lane.
- `https://github.com/Tencent-Hunyuan/Hy3`: reasoning/model-agent evidence, not a skill workflow activation lane.

## Change

- Added explicit `github-growth-20260708T123852.626885Z` pass-1 route specs in `src/blackhole_agent/skill_routing.py`.
- Kept adjacent general-agent/workflow/model repositories in `agent_harness_eval_required` with no direct local lanes before harness evaluation.
- Made `implementation_lane_selected: false` explicit on pass-1 adjacent rows.
- Added a local harness fixture and focused tests for the current digest.
- Updated aggregate local harness fixture totals.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260708T123852`
- `pytest tests/test_harness_eval.py -q -k 20260708T123852`
- `pytest tests/test_harness_eval.py -q -k "20260708T123852 or local_harness_eval_runs_pass_and_fail"`
- `pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k "20260708T100635 or 20260708T123852"`

All listed validation commands passed.

## Review Notes

- No external activation, install, provider launch, harness execution, remote execution, or raw upstream body export was added.
- The self-model was read and left unchanged because the current preference already matched the run: prefer rollback-backed local behavior changes with validation over standalone reports.
