# Blackhole Run: skill-route-discovery pass 2 local route eval gate

- Source digest: `github-growth-20260708T233850.660413Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T233848Z-pass2-skill-route-discovery`
- Rollback artifact: `artifacts/rollback/20260708T233848Z-pass2-skill-route-discovery.md`
- Self-model decision: unchanged

## Evidence

- `lingbol088-spec/reverse-flow-skill` exposes a Codex/AI Agent skill workflow shape with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, staged analysis language, install/run examples, and scripts. This is useful route evidence, but install/run pressure remains disabled.
- `Pluviobyte/rnskill` exposes a generic SKILL.md-compatible multi-skill collection with docs, tools, and plugin/marketplace install pressure. This maps to documentation-first skill-route discovery, not activation.
- `shepherd-agents/shepherd` is a general reversible agent runtime substrate. It remains adjacent `agent_harness_eval_required` until local harness evaluation passes.

## Hypothesis

Pass-2 route discovery should expose a local route eval gate that proves skill-route evidence is bounded before activation and that adjacent general-agent evidence cannot inherit direct implementation lanes.

## Changes

- Added `current_digest_20260708T233850_pass2_validation_lane` for the active source digest.
- Added `local_route_eval_gate` to the pass-2 validation lane helper.
- Added a frozen current-digest fixture and focused regression test.
- Documented the operator-visible route eval gate.

## Validation

`python -m pytest tests/test_skill_routing.py -q -k 20260708T233850`

Result: passed, 1 passed.

## Review Notes

- The packet remains metadata-only and hash/body-free.
- Activation, install, run, provider launch, external harness execution, remote execution, profile writes, and memory writes remain disabled.
- The self-model was left unchanged because its current preference already matches this run's rollback-backed local validation behavior.
