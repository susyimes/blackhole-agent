# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260709T051527.252839Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/rollback/20260709T051525Z-skill-route-discovery-pass2`
- Hypothesis: skill-workflow evidence is more useful when the controller exposes the interpretation path before activation, not only the selected lane.

## Change

Added `current_pass2_skill_workflow_interpretation_path` to the route lane map and nested pass-2 handoff. It records the ordered interpretation path for skill/workflow repositories:

1. classify the public skill/workflow signal;
2. bind it only to documentation, config, test, or code_patch;
3. require focused local validation;
4. require controller approval before runtime action.

The active reverse-flow/rnskill window remains metadata-only. Adjacent agent-chief and Hy3 evidence stays in `agent_harness_eval_required`.

## Safety Notes

No install, clone-and-run, provider launch, profile write, memory write, external harness execution, remote execution, raw source URL export, or upstream body export path was added.

## Validation

Passed:

```powershell
python -m pytest tests/test_github_growth.py -q -k current_pass2_skill_workflow_interpretation_path
python -m pytest tests/test_github_growth.py tests/test_proposal_eval.py -q -k "current_pass2_lane_handoff or current_pass2_skill_workflow_interpretation_path"
```

The second command also covered nearby route classifier and skill-workflow route-hint regressions in this run.
