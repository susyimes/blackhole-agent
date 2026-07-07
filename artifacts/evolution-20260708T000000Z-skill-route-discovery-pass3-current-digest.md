# Evolution Report: skill-route-discovery pass 3 current digest

- Source digest: `github-growth-20260707T190110.064980Z`
- Capability slice: skill-route-discovery
- Rollback artifact: `artifacts/rollback/20260708T000000Z-skill-route-discovery-pass3-current-digest/rollback-point.md`
- Rollback ref: `refs/rollback/20260708T000000Z-skill-route-discovery-pass3-current-digest`
- Self-model decision: unchanged; the existing preference for rollback-backed local validation already matches this run.

## Evidence Review

- `lingbol088-spec/reverse-flow-skill` exposes a `skills/reverse-flow` package shape, `SKILL.md` workflow framing, local sandbox/CTF boundaries, and diagnostic scripts. It remains Codex workflow-gate skill evidence in the bounded local test lane.
- `Pluviobyte/rnskill` exposes `skills/`, docs, tools, marketplace-style metadata, and install examples for `SKILL.md`-compatible workflows. It remains generic skill collection evidence in the bounded documentation lane.
- `shepherd-agents/shepherd` describes a reversible agent runtime with retained outputs, replay, and supervision. It remains adjacent agent-harness evidence, not a skill-route lane or runtime path.

## Local Change

- Extended the pass-3 route-to-validation dispatcher to recognize `github-growth-20260707T190110.064980Z`.
- Added a pass-3 operator-visible activation-review packet for the current reverse-flow/rnskill/Shepherd window.
- The pass-3 lane now advances the existing pass-2 current digest mapping rather than inferring from the older pass-1 shape.
- Added regression coverage proving reverse-flow and rnskill stay in bounded local lanes while Shepherd, Agents-A1, Fundamental-Ava, and Shepherd PR activity remain behind agent-harness evaluation.
- Updated `docs/skill-route-discovery.md` with the pass-3 replay contract.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T190110`
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T190110 or 20260707T180109 or 20260707T164109"`

## Review Notes

- No upstream repository was cloned, installed, or executed.
- No external skill activation, external harness execution, provider launch, remote execution, memory write, profile write, restart, promotion, or push was performed.
- Raw source URLs and replay commands are accepted in fixture input but must not appear in controller output; the regression checks this.
