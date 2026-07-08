# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260708T141851.976489Z`
- Branch: `codex/blackhole-evolve/20260708T142000.961650-add-or-run-a-bounded-skill-route-discovery-valid`
- Rollback ref: `refs/blackhole/rollback/20260708T141849Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260708T141849Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: public repository review found a Codex/AI Agent skill package with `skills/reverse-flow`, `SKILL.md`, local sandbox/CTF framing, staged workflow language, install examples, and script examples. Treated as test-lane route evidence only.
- `Pluviobyte/rnskill`: public repository review found a generic AI Agent skills collection. Treated as documentation-lane metadata evidence while the local proposal remains a test probe.
- `shepherd-agents/shepherd` and issue 38: public review indicates reversible runtime substrate and coding-agent integration pressure. Treated as adjacent `agent_harness_eval_required` only.

## Hypothesis

The active pass-2 slice benefits from a first-class controller-visible lane for the current digest instead of another standalone validation note. The lane should map skill evidence into documentation/test lanes, hold Shepherd/Hy3/workflow evidence behind local harness evaluation, and export only body-free replay metadata plus activation denials.

## Changes

- Added `github-growth-20260708T141851.976489Z` to the existing pass-2 skill-route validation lane family.
- Added current proposal IDs for reverse-flow, rnskill, Shepherd integration, Hy3 MCP probe, and general agent-project triage policy.
- Added regression coverage proving the lane stays bounded and records this run's rollback ref/artifact.
- Documented the new controller surface and replay command.

## Review Notes

- No upstream code was installed, cloned, or executed.
- No raw source URLs, evidence URLs, replay commands, target paths, or upstream bodies are exported by the lane payload.
- Self-model left unchanged: its current preference already supports rollback-backed, locally validated behavior changes and keeps offensive behavior/privacy leakage review-only.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T141851` passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T141851 or 20260708T125853 or 20260708T131852"` passed.
