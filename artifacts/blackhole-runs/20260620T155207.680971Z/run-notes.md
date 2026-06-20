# Run Notes

Run: github-growth-20260620T155207.680971Z
Branch: codex/blackhole-evolve/20260620T155317.225238-add-or-update-a-local-skill-route-discovery-cata
Rollback ref: refs/blackhole-rollback/20260620T155317.225238

## Evidence And Hypothesis

The carried evidence URLs describe skill-like public repositories that should inform local route discovery but not become executable workflows. This pass is inside the provider-runtime-control window, so the useful local improvement is an operator-visible catalog that links bounded skill-route profiles to local validation lanes and provider-runtime replay requirements.

Hypothesis: a body-free `route_discovery_catalog` in the existing `skill_route_discovery_lane` output improves supervisor handoff by showing selected local lanes and provider-runtime replay gates without exporting upstream URLs, upstream bodies, target paths, or permitting runtime execution.

## Material Actions

- Created rollback ref `refs/blackhole-rollback/20260620T155317.225238`.
- Added `route_discovery_catalog` to the skill-route harness output.
- Added focused regression coverage for provider-runtime-control catalog readiness.
- Documented the catalog surface in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged. It already states that local evolution should prefer validated behavior changes over ornamental reports; this run had a concrete harness behavior improvement and did not need a self-model revision.

## Validation

- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_catalog or skill_route_discovery_provider_runtime_control_pass or skill_route_discovery_pass3_selects"`: passed, 4 passed.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or provider_runtime_preflight or provider_runtime_recovery_summary or proposal_interpretation"`: passed, 24 passed.
- `pytest tests/test_harness_eval.py -q`: passed, 107 passed.

## Review Notes

The catalog remains metadata-only. It maps observed route profiles to documentation, config, test, or code_patch lanes, preserves selected digest item IDs, hashes candidate sources, requires local validation and provider-runtime replay where applicable, and denies external skill activation, external harness execution, provider launch, remote execution, raw source URL export, raw target path export, and upstream body export.
