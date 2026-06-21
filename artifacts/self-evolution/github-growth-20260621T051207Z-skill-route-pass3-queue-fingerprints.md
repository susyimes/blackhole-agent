# Skill Route Pass 3 Queue Fingerprints

- Source digest: `github-growth-20260621T051207.876517Z`
- Capability theme: `skill-route-discovery`
- Capability pass: 3 of 4
- Branch: `codex/blackhole-evolve/20260621T051315.354258-add-or-extend-local-validation-that-detects-and-`
- Rollback ref: `refs/rollback/20260621T051207Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/rollback/20260621T051207Z-skill-route-discovery-pass3.md`

## Evidence And Hypothesis

The carried evidence window combines COMPASS Skills, Three.js Game Skills, and
FableCodex-style mixed skill/workflow routes. Existing local behavior already
keeps these repositories inside bounded documentation, config, test, and
code_patch lanes and exposes pass-3 replay packets.

Hypothesis: the pass-3 replay queue should expose stable body-free fingerprints
for each selected or queued local lane, so a supervisor can detect queue drift
between handoff surfaces without comparing raw source URLs, target paths,
replay command bodies, or upstream skill bodies.

## Change

- Added `queue_fingerprint` and `fingerprint_basis` to each
  `pass_validation_replay_queue` row.
- Added top-level `queue_fingerprints` to the replay queue.
- Propagated the same fingerprint fields through pass-2 and pass-3 handoff row
  copies.
- Documented that fingerprints are drift identifiers only and do not authorize
  install, enable, run, clone, scaffold, provider launch, remote execution, or
  upstream skill activation.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3_selects_bounded_lane_per_profile"`:
  passed, 1 test.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`:
  passed, 9 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`:
  passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k "skill_route_discovery or mixed"`:
  passed, 15 tests.
- `python -m ruff check src/blackhole_agent/harness_eval.py tests/test_harness_eval.py`:
  passed.

## Review Notes

- No external skill code was imported, installed, cloned, or executed.
- The self-model was read and left unchanged because it already matches this
  run's direct, rollback-backed, locally validated behavior change.
- The fingerprints are derived only from already-sanitized queue metadata:
  queue role, bounded lane, validation scope, route profiles, selected item
  IDs, candidate source hashes, and denied runtime/external activation flags.
