# Runner Harness Control Pass 3

Source digest: `github-growth-20260624T071355.650148Z`

Rollback point:

- Ref: `refs/blackhole-rollback/20260624T071354Z-runner-harness-control-pass3`
- Artifact: `artifacts/rollback/20260624T071354Z-runner-harness-control-pass3.md`

## Hypothesis

The active runner-harness-control slice needs one operator-visible workflow
rather than another isolated route fixture. The pass-3 skill-route handoff
already has bounded lane selection, profile validation proof, a promotion
runbook, and activation proof. Turning those existing surfaces into a
five-stage control-plane summary makes intake, mid-flight state, recovery,
replay, and report status inspectable end to end without adding activation
authority.

## Change

- Added `skill_route_discovery_pass3_control_plane` to derive a body-free
  runner workflow summary from pass-3 artifacts.
- Included `runner_harness_control_plane` in `pass3_handoff_packet`.
- Extended pass-3 tests for both ready and blocked profile-contract paths.
- Documented the new pass-3 control-plane field in
  `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3"`:
  passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`:
  passed, 2 tests.
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`:
  passed, 9 tests.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference for
rollback-backed, locally validated behavior changes matches this run, and the
new evidence did not require a more specific self-description.

## Review Notes

Evidence URLs were used only as carried digest context; no broad trend
rediscovery was run. The new control plane exports artifact-name hashes and
command hashes only, keeps raw evidence/source/target/artifact paths out of
the packet, and continues to deny runtime action, external skill activation,
external harness execution, provider launch, and remote execution.
