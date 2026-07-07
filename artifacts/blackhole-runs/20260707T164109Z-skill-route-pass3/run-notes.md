# Run Notes

Run: `20260707T164109Z-skill-route-pass3`
Branch: `codex/blackhole-evolve/20260707T164145.532523-add-or-extend-a-local-skill-route-discovery-vali`
Source digest: `github-growth-20260707T164109.440819Z`
Theme: `skill-route-discovery`

## Evidence

Focused evidence review used the carried digest and proposal URLs only:

- `https://github.com/Pluviobyte/rnskill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/InternScience/Agents-A1`
- `https://github.com/shepherd-agents/shepherd`

The evidence supports a bounded route split: skill/workflow repositories can
be validation candidates for documentation, config, test, or code_patch lanes;
general agent projects need local agent-harness evaluation before any follow-up
lane is selected.

## Hypothesis

The active pass-3 window needs an operator-visible lane for the exact current
digest, not another generic fixture. The controller should recompute scope and
gates from local route evidence, ignore candidate-supplied scope/gate wording,
and keep activation, runtime action, provider launch, external harness
execution, memory writes, remote execution, raw URLs, raw commands, and upstream
bodies disabled.

## Changes

- Added `skill_route_discovery_current_digest_20260707T164109_pass3_validation_lane`.
- Wired `github-growth-20260707T164109.440819Z` into the pass-3 route-to-validation dispatcher.
- Added a frozen fixture for the current digest.
- Added focused routing and documentation contract tests.
- Updated `docs/skill-route-discovery.md` with the pass-3 interpretation rule.

## Self-Model Decision

`docs/self-model.md` was left unchanged. It already states the preference used
in this run: local evolution should be rollback-backed, locally validated, and
explicit about uncertainty, while validation reports are evidence artifacts
rather than the default destination.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T164109`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k 20260707T164109`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T160109 or 20260707T164109 or 20260707T154109"`: passed, 3 tests.

## Review Notes

- No offensive behavior, unauthorized access, privacy leakage, provider launch,
  remote execution, external harness execution, or memory-write route was added.
- External evidence review was narrow and did not rerun trend discovery.
- Activation remains a supervisor concern after local validation and artifact
  handoff.
