# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260701T200302.486485Z`
- Theme: `skill-route-discovery`
- Rollback point: `artifacts/rollback/20260701T200301Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/20260701T200301Z-skill-route-discovery-pass2`

## Evidence

Focused public evidence review used only the carried proposal URLs:

- `https://github.com/lyra81604/zhengxi-views`: repository page shows `SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`, source-cited research workflow, and a non-investment-advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`: general agent evaluation project evidence, not a skill-route package signal for this pass.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: general autonomous agent project evidence, not a skill-route package signal for this pass.
- `https://github.com/ksimback/looper`: review-gated agent loop project evidence, not a skill-route package signal for this pass.

## Hypothesis

Evidence items should not need hand-written `route_classification` metadata to expose a bounded skill package route. If a digest item already carries body-free `observed_paths` and `metadata_files`, blackhole-agent can infer local lane signals from those paths, surface a progressive skill package validation contract, and still keep activation blocked behind local validation and rollback.

## Change

- `ExternalSkillEvidenceItem` now carries `observed_paths` and `metadata_files`.
- Evidence-item registry construction now derives layout and metadata signals from those fields, including `progressive_skill_package` when `SKILL.md`, a skill manifest, and references are present.
- The local harness output now exports sanitized `source_layout_signals`, `source_metadata_signals`, and `progressive_skill_package_contract` on proposal lanes.
- Added a pass-2 local harness fixture for source digest `github-growth-20260701T200302.486485Z`.
- Updated documentation for the pass-2 operator-visible behavior.

## Safety Boundary

No upstream code was cloned, installed, imported, or executed. General-agent projects without skill route hints remain outside `skill_route_discovery` and require `agent_harness_eval` before follow-up lanes. Runtime action, external skill activation, external harness execution, provider launch, remote execution, raw URL export, and upstream body export remain denied.

## Validation

Initial focused validation:

```powershell
pytest tests/test_skill_routing.py -q -k "progressive or evidence_items_infer"
pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs"
```

Both commands passed after repairing the evidence-item grouping path.

Final validation:

```powershell
pytest tests/test_skill_routing.py tests/test_harness_eval.py -q
```

Result: 347 passed.
