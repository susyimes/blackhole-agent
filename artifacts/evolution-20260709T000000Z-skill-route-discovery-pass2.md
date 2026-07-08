# Skill Route Discovery Pass 2

Source digest: `github-growth-20260708T165850.561086Z`
Theme: `skill-route-discovery`
Rollback artifact: `artifacts/rollback/20260709T000000Z-skill-route-discovery-pass2/rollback-point.md`
Rollback ref: `refs/rollback/blackhole-agent/20260709T000000Z-skill-route-discovery-pass2`

## Hypothesis

The active reverse-flow/rnskill window already has enough local route evidence
to advance from pass-1 discovery to a pass-2 operator-visible validation lane.
The lane should expose only bounded local outputs for skill/workflow
repositories and should hold Hy3/Shepherd-style general-agent evidence behind
`agent_harness_eval_required`.

## Evidence Used

- `lingbol088-spec/reverse-flow-skill`: Codex workflow-gate skill evidence.
- `Pluviobyte/rnskill`: generic SKILL.md workflow evidence.
- `Tencent-Hunyuan/Hy3`: adjacent model/provider/general-agent project evidence.
- `shepherd-agents/shepherd`: adjacent runtime-substrate/general-agent evidence.

No broad trend discovery was rerun. External evidence remains represented by
frozen digest item IDs and body-free summaries.

## Change

- Added `current_digest_20260708T165850_pass2_validation_lane.json` as a frozen
  local fixture.
- Extended `current_digest_pass2_local_validation_lane` routing to recognize
  `github-growth-20260708T165850.561086Z`.
- Added a regression that asserts reverse-flow/rnskill map only to
  documentation, config, test, or code_patch lanes while Hy3/Shepherd remain
  behind `agent_harness_eval_required`.
- Documented the new pass-2 operator lane.

## Validation

Local replay completed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T165850
python -m pytest tests/test_skill_routing.py -q -k 20260708T153850
python -m pytest tests/test_docs_contracts.py -q
```

Results:

- `20260708T165850`: 1 passed, 427 deselected.
- `20260708T153850`: 1 passed, 427 deselected.
- Docs contracts: 27 passed.
