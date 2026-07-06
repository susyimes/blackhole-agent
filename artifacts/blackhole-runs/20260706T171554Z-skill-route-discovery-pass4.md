# Blackhole Run: skill-route-discovery pass 4

Source digest: `github-growth-20260706T171555.486656Z`

Rollback artifact: `artifacts/rollback/20260706T171554Z-skill-route-discovery-pass4.md`

Rollback ref: `refs/blackhole-rollback/20260706T171554Z-skill-route-discovery-pass4`

## Hypothesis

The current reverse-flow skill-route window should end with an operator-visible
pass-4 handoff for the latest digest. Reverse-flow skill workflow evidence may
advance only through bounded local lanes, while adjacent general-agent projects
must remain behind `agent_harness_eval_required` before any implementation or
runtime adoption.

## Changes

- Added a `github-growth-20260706T171555.486656Z` branch to the existing
  reverse-flow pass-4 completion helper.
- Added a frozen fixture for the latest digest with one reverse-flow skill row
  and four adjacent general-agent rows.
- Added a regression test that verifies bounded skill-route lanes, no inherited
  skill route for general-agent rows, no runtime/provider/external harness
  activation, and body-free controller output.
- Documented the current digest's route-policy distinction in
  `docs/skill-route-discovery.md`.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260706T171555
python -m pytest tests/test_skill_routing.py -q -k "20260706T171555 or 20260706T163555 or 20260706T155555"
```

Both commands passed.

## Review Notes

- The self-model was left unchanged. Its current preference already covers this
  run's behavior; adding digest-specific route details there would make it less
  useful as a compact self-description.
- No external fetch, restart, push, provider launch, remote execution, profile
  write, or memory write was performed.
