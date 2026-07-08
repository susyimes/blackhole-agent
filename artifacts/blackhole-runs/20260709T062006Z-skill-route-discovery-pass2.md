# Skill Route Discovery Pass 2 Run Note

- Source digest: `github-growth-20260708T221850.808872Z`
- Theme: `skill-route-discovery`
- Rollback ref: `refs/blackhole-rollback/20260709T062006Z-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback/20260709T062006Z-skill-route-discovery-pass2/rollback-point.md`

## Evidence Reviewed

- `Pluviobyte/rnskill`: public AI Agent Skills collection with `skills`, docs,
  tools, plugin-style metadata, Codex/Claude-compatible `SKILL.md` workflow
  language, and install pressure.
- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent reverse-flow
  skill with `skills/reverse-flow`, `SKILL.md`, local sandbox and CTF framing,
  staged workflow language, and diagnostic scripts.

## Hypothesis

The current pass should expose an operator-visible local validation lane rather
than another standalone fixture. Reverse-flow and rnskill should route first
through `skill_route_discovery` and remain bounded to documentation, config,
test, or code_patch lanes. Shepherd and Hy3 should stay adjacent
`agent_harness_eval_required` rows until local harness evidence exists.

## Local Changes

- Added `current_digest_20260708T221850_pass2_validation_lane` fixture and test.
- Parameterized the existing current-digest pass-2 validation helper so this
  run can reuse the same route packet without duplicating routing logic.
- Documented the local decision rule for the current digest using digest,
  proposal, and item IDs.
- Left `docs/self-model.md` unchanged because its current preference already
  matches this run: rollback-backed local validation before activation.

## Validation

Planned focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260708T221850
```

No activation, external skill install, external harness execution, provider
runtime launch, promotion, push, or restart was performed by this kernel run.
