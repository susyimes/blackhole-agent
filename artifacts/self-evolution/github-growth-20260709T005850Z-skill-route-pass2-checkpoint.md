# Evolution Run: skill-route-discovery pass 2 checkpoint

Source digest: `github-growth-20260709T005850.776521Z`
Branch: `codex/blackhole-evolve/20260709T005934.830701-add-a-bounded-skill-route-discovery-validation-c`
Rollback ref: `refs/rollback/20260709T005850Z-skill-route-discovery-pass2`
Rollback artifact: `artifacts/rollback/20260709T005850Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow repository with `skills/reverse-flow`, `SKILL.md`, local sandbox framing, staged reverse-analysis workflow, scripts, and install/run pressure treated as non-activation evidence.
- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection for Codex/Claude-style `SKILL.md` workflows, with `skills`, `docs`, `tools`, marketplace/plugin metadata, and install examples.
- `https://github.com/eli-labz/Cognitive-Core-Skills`: public cognitive skill taxonomy repository with generated skill cards, schemas, benchmarks, validation tests, and CI.

## Hypothesis

Pass 2 should expose an operator-visible checkpoint rather than another
standalone fixture. Mixed skill plus benchmark evidence should validate through
`skill_route_discovery` first, keep the local lanes bounded to documentation,
config, test, or code_patch, and allow agent-harness evaluation only as a
blocked follow-up after local skill-route validation.

## Changes

- Added `current_pass2_skill_benchmark_checkpoint` to the validation route
  packet for this source digest.
- Added a regression for reverse-flow, rnskill, and Cognitive-Core-Skills
  evidence proving bounded lanes, `skill_route_discovery_first`, and no direct
  agent-harness lane before skill-route validation.
- Documented the pass-2 checkpoint and added a docs contract assertion.

## Self-Model Decision

`docs/self-model.md` was left unchanged. The current text already says to prefer
rollback-backed, locally validated behavior improvements over ornamental
self-description edits, which matches this run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260709T005850`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260709T003850 or 20260709T005850"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k 20260709T005850`: passed, 1 test.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py tests/test_docs_contracts.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 446 tests.

## Review Notes

- No upstream code, skill package, installer, script, provider, harness, or
  remote execution path was installed or run.
- Raw source URLs, raw evidence URLs, replay commands, target paths, upstream
  bodies, promotion, and restart remain disabled in the checkpoint.
- The Cognitive-Core-Skills benchmark signal remains secondary and blocked
  until local skill-route validation succeeds.
