# Evolution Run: skill-route-discovery pass 1 domain guard

- Source digest: `github-growth-20260707T212110.239635Z`
- Capability slice: `skill-route-discovery`
- Prepared branch: `codex/blackhole-evolve/20260707T212157.837305-run-a-bounded-local-skill-route-discovery-valida`
- Rollback ref: `refs/blackhole/rollback/20260707T212110Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260707T212110Z-skill-route-discovery-pass1/rollback-point.md`
- External evidence reviewed: `lingbol088-spec/reverse-flow-skill`, `Pluviobyte/rnskill`, `NVIDIA-BioNeMo/bionemo-agent-toolkit`, `InternScience/Agents-A1`

## Hypothesis

The current pass-1 route-discovery window should expose a single replayable lane
that validates three skill-route profiles before activation: reverse-flow as a
Codex workflow-gate test candidate, rnskill as a generic skill collection
documentation candidate, and BioNeMo as a domain-specific skill toolkit guard.
Adjacent general-agent repositories should remain queued for agent-harness
evaluation and should not inherit skill-route lanes.

## Change

- Added the `github-growth-20260707T212110.239635Z` digest to
  `skill_route_discovery_current_pass1_focused_review_lane`.
- Added a fixture for the active reverse-flow, rnskill, BioNeMo, Agents-A1, and
  Shepherd evidence window.
- Added a regression test proving BioNeMo remains bounded to documentation,
  config, test, or code_patch lanes with provider/runtime activation denied.
- Documented the current pass-1 lane in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already
supports rollback-backed, locally validated behavior changes, and this run had a
concrete route-discovery behavior path. Editing the self-model would have been
ornamental rather than behavior-shaping.

## Validation

Local replay completed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T212110
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_20260707T212110
python -m pytest tests/test_skill_routing.py -q -k "20260707T212110 or 20260707T200110"
```

Results: all selected tests passed.

No promotion, push, restart, provider launch, external harness execution,
runtime execution, or upstream repository clone was performed by this kernel.
