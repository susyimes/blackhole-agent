# Skill Route Discovery Pass 3 Candidate Registry

- source_digest: github-growth-20260703T010121.773810Z
- branch: codex/blackhole-evolve/20260703T010215.950488-create-a-local-validation-lane-that-probes-rever
- rollback_artifact: artifacts/self-evolution/github-growth-20260703T010121Z-rollback.md
- rollback_ref: refs/blackhole-rollback/20260703T010121Z-skill-route-discovery-pass3
- self_model: read and left unchanged

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill
- https://github.com/lyra81604/zhengxi-views

The reverse-flow repository was treated as public Codex/AI Agent skill-route
evidence: a `skills/reverse-flow/SKILL.md` package shape, scripts, local
sandbox/CTF/crackme workflow framing, install examples, and fork pressure.
This evidence supports bounded local route discovery only, not upstream skill
installation or execution.

## Hypothesis

A pass-3 operator surface should validate item-level candidate registry metadata
before final activation review. The registry should prove that reverse-flow and
source-cited skill items map only to documentation, config, test, or code_patch
lanes, while omitting raw URLs, upstream bodies, target paths, commands, and any
runtime activation authority.

## Changes

- Added `skill_route_discovery_candidate_registry_lane` to the local harness
  evaluator.
- Added a current-digest fixture for reverse-flow and zhengxi item-level
  registry metadata.
- Updated aggregate local harness expectations for the added fixture.
- Documented the current pass-3 registry decision rule.

## Validation

- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`
- `pytest tests/test_harness_eval.py -q -k proposal_interpretation`
- `pytest tests/test_harness_eval.py -q`

All validation passed.

## Review Notes

- The registry lane is local metadata only and reports raw item IDs, source URLs,
  evidence URLs, upstream bodies, provider launch, external harness execution,
  external skill activation, and remote execution as not exported or denied.
- Fork rows remain lineage pressure, not independent implementation authority.
- No self-model edit was made because the existing self-model already describes
  this run's rollback-backed local-evolution stance and does not need a new
  behavior claim.
