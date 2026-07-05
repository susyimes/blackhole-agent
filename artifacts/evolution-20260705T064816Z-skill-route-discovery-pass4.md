# Evolution Run: skill-route-discovery pass 4

- Source digest: `github-growth-20260705T064819.468069Z`
- Branch: `codex/blackhole-evolve/20260705T064907.707465-add-a-local-skill-route-discovery-validation-lan`
- Rollback ref: `refs/blackhole-rollback/20260705T064816Z-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260705T064816Z-skill-route-discovery-pass4/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public Codex-oriented skill/workflow repository with install, script, and reverse-flow runtime pressure; interpreted only as local skill-route evidence.
- `NVIDIA-BioNeMo/bionemo-agent-toolkit`: public agent toolkit with skill/catalog/workflow signals; interpreted only as generic skill-workflow route evidence.
- `QwenLM/Qwen-AgentWorld` and `TianhangZhuzth/Fundamental-Ava`: general-agent project evidence without local harness results; routed to `agent_harness_eval_required`.

## Hypothesis

The final pass should expose an operator-visible completion handoff for the
current digest rather than another standalone fixture. The handoff should bind
reverse-flow and BioNeMo skill/workflow evidence to bounded local lanes, keep
general-agent projects behind agent-harness evaluation, and deny external
activation, runtime execution, provider launch, raw upstream export, and remote
execution.

## Changes

- Added a rollback point for this run.
- Registered `github-growth-20260705T064819.468069Z` with the generalized
  pass-4 skill-route completion handoff.
- Added a focused fixture and regression test for the current digest.
- Documented the operator-visible pass-4 completion lane.
- Left `docs/self-model.md` unchanged because its current preference already
  matches this run's locally validated behavior path.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260705T064819
python -m pytest tests/test_skill_routing.py -q -k "20260705T040819 or 20260705T052819 or 20260705T064819"
python -m pytest tests/test_docs_contracts.py -q -k skill_route
```

All validation commands passed.

## Review Notes

- No upstream code was installed, cloned for execution, imported, or run.
- The handoff remains body-free and record-only for the external supervisor.
- General-agent projects still require local agent-harness evaluation before
  documentation, test, or code_patch follow-up can be considered.
