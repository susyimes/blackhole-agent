# Blackhole Run: skill-route-discovery pass 1

- Source digest: `github-growth-20260707T224110.380959Z`
- Branch: `codex/blackhole-evolve/20260707T224203.774101-add-or-run-a-local-skill-route-discovery-validat`
- Rollback artifact: `artifacts/rollback/20260707T224108Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260707T224108Z-skill-route-discovery-pass1`

## Hypothesis

Codex-oriented and generic public skill workflow evidence should stay in
bounded local lanes before activation. A compact pass-1 activation gate derived
from existing route evidence improves supervisor review because it exposes one
ready/blocked decision without permitting install, runtime execution, provider
launch, external harness execution, remote execution, or raw upstream export.

## Evidence Notes

The carried proposal evidence named `lingbol088-spec/reverse-flow-skill` as a
Codex workflow-gate skill route and `NVIDIA-BioNeMo/bionemo-agent-toolkit` plus
`Pluviobyte/rnskill` as generic skill workflow pressure. This run did not
expand beyond the provided evidence URLs; it used the repository's existing
frozen fixtures and route classifiers as the local validation source.

## Changes

- Added `active_pass1_activation_gate` to the skill-route proposal lane map.
- Exposed the gate through `skill_route_discovery_lane` harness output.
- Documented the gate in `docs/skill-route-discovery.md`.
- Extended active pass-1 harness and documentation contract tests.
- Left `docs/self-model.md` unchanged because its current preference for
  rollback-backed, locally validated behavior changes matched this run.

## Validation

- `pytest tests/test_harness_eval.py -q -k active_pass1_proposal_replay_lane`: passed.
- `pytest tests/test_skill_routing.py -q -k active_pass1`: passed.
- `pytest tests/test_harness_eval.py -q -k "active_pass1_proposal_replay_lane or 20260703T153924_pass1_validation_lane"`: passed.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records`: passed.

## Review Notes

The new gate is metadata-only. Activation authority remains
`external_supervisor_after_validation`, and the gate records no raw source URLs,
evidence URLs, target paths, upstream bodies, replay commands, provider launch,
external harness execution, or remote execution.
