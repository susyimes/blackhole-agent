# Skill Route Discovery Pass 2 Current Window

- Source digest: `github-growth-20260707T121946.674633Z`
- Capability slice: `skill-route-discovery`, pass 2 of 4
- Rollback artifact: `artifacts/rollback/20260707T121944Z-skill-route-discovery-pass2-current-window/rollback-point.md`
- Rollback ref: `refs/rollback/20260707T121944Z-skill-route-discovery-pass2-current-window`

## Hypothesis

The current evidence window is strong enough for an operator-visible pass-2
validation lane rather than another standalone checklist. Reverse-flow-style
Codex workflow evidence should validate first through `skill_route_discovery`;
rnskill-style generic skill collections should map to documentation and route
classification coverage; general agent projects should remain behind local
agent-harness evaluation.

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository
  with `skills/reverse-flow`, `SKILL.md`-oriented package shape, local sandbox
  framing, CTF/crackme context, scripts, and install/run examples.
- `https://github.com/Pluviobyte/rnskill`: public multi-skill collection for
  Codex, Claude Code, and `SKILL.md`-compatible workflows, with `skills/`,
  docs, tools, marketplace metadata, and manual install examples.
- `https://github.com/shepherd-agents/shepherd`: public general agent runtime
  with reversible trace, fork, replay, revert, permissions, and retained-output
  claims.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public autonomous agent
  simulation project with memory, collaboration, social behavior, experiments,
  and benchmark-style claims.

## Local Change

- Added `skill_route_discovery_current_digest_20260707T121946_pass2_validation_lane`.
- Added a frozen fixture for the current digest.
- Added focused regression coverage for route selection, bounded outputs,
  agent-harness gating, rollback metadata, and body-free controller output.
- Documented the pass-2 replay path in `docs/skill-route-discovery.md`.

## Review Notes

- No upstream skill, package, script, runtime, provider, or harness was
  installed, enabled, cloned, or executed.
- Controller output keeps raw source URLs, raw evidence URLs, upstream bodies,
  target paths, and validation commands out of exported lane metadata.
- `docs/self-model.md` was left unchanged. It already prefers rollback-backed,
  locally validated evolution over ornamental self-model edits, which matches
  this run.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260707T121946
```

Passed:

```powershell
python -m pytest tests/test_skill_routing.py -q
```
