# Skill Route Discovery Pass 2 Fixture Validation

- Source digest: `github-growth-20260627T120310.659503Z`
- Branch: `codex/blackhole-evolve/20260627T120421.839045-add-or-extend-local-validation-tests-for-generic`
- Rollback artifact: `artifacts/rollback/20260627T120421Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260627T120421-skill-route-pass2`

## Evidence Reviewed

External review was bounded to the carried proposal URLs:

- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/dongshuyan/compass-skills`

The reusable lesson was to accept compact route-classification metadata as local
fixture evidence only, then validate it through bounded lanes before activation.
The review did not import upstream code, clone repositories, run upstream
scripts, install external skills, launch providers, or execute external
harnesses.

## Local Change

The local route candidate loader now accepts nested `route_classification`
metadata for route hints, route profiles, bounded lanes, and layout or metadata
signals. The normal registry checks still apply: public GitHub source only,
disabled by default, unsupported lanes downgraded or rejected, and no runtime
action.

The lane map now emits `pass2_fixture_validation_lane`, an operator-visible
packet that checks each frozen route fixture for route class, bounded selected
lane, selected item IDs or fixture evidence, and preserved
`local_validation_required: true`.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "pass2_route_classification_fixture or current_pass2_focused_evidence_review or current_pass_validation_cases"
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

## Review Notes

- `docs/self-model.md` was read and left unchanged. Its current preference for
  rollback-backed, locally validated behavior changes matches this run.
- Unsupported fixture lanes such as `provider_runtime`, `runtime_execution`, and
  `install` remain downgraded out of proposal lanes.
- Activation, provider launch, external harness execution, remote execution,
  raw source URL export, raw target path export, and upstream body export remain
  denied in the new pass-2 validation lane.
