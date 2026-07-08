# Skill Route Discovery Pass 2 Reverse-Flow/Rnskill Lane Validation

Source digest: github-growth-20260708T074636.681420Z
Run timestamp: 20260708T074633Z
Rollback ref: refs/blackhole/rollback/20260708T074633Z-skill-route-discovery-pass2-reverse-flow-rnskill-lane-validation
Rollback artifact: artifacts/rollback/20260708T074633Z-skill-route-discovery-pass2-reverse-flow-rnskill-lane-validation/rollback-point.md

## Evidence

- https://github.com/lingbol088-spec/reverse-flow-skill: public repository metadata showed `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, install/run examples, 444 stars, and 216 forks at review time.
- https://github.com/Pluviobyte/rnskill: public repository metadata showed a generic AI Agent Skills collection with `skills`, docs, tools, `.claude-plugin`, marketplace/install examples, 369 stars, and 36 forks at review time.

## Hypothesis

The repository lane probe should be the first operator-visible validation lane
for current reverse-flow/rnskill evidence. It should detect skill instruction
files, manifests or marketplace metadata, allowed local lanes, unsupported
install/run pressure, and fork lineage before activation packets are built.
Forks of the same upstream skill should support one row rather than multiply
identical proposals.

## Changes

- `build_skill_route_discovery_repository_lane_probe` now collapses candidate
  summaries by lineage before emitting candidate rows.
- Candidate rows now include supporting summary counts, supporting candidate
  names, supporting source hashes, and uncertainty reasons.
- The probe reports `duplicate_candidate_summary_count` and
  `fork_lineage_collapsed`.
- The pre-activation probe keeps generic Codex-compatible marketplace catalogs
  in generic skill-workflow lanes unless workflow-gate markers are present.
- Added regression coverage for current reverse-flow plus fork metadata,
  `Pluviobyte/rnskill`, and an adjacent workflow-usecase repository.
- Documented the fork-collapse and generic catalog lane boundary.
- Left `docs/self-model.md` unchanged because the current self-model already
  supports rollback-backed local behavior changes and the safety boundary used
  by this run.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "repository_lane_probe"`: passed, 2 tests.
- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q`: passed, 412 tests.
- `PYTHONPATH=src python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`: passed, 17 tests.
- `git diff --check`: passed with LF-to-CRLF working-copy warnings only.

## Review Notes

- No upstream code was cloned, installed, imported, or executed.
- Unsupported install, run, provider, runtime, and remote-execution pressure is
  retained only as stripped diagnostic metadata.
- The probe exports hashes and counts for supporting sources; raw source URLs
  remain outside the operator-facing probe output.
- Hy3 MCP/tool-routing behavior remains review-only for privacy-leakage
  boundary reasons in this pass.
