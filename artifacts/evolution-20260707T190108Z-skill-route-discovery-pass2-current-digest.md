# Evolution Report: skill-route-discovery pass 2 current digest

- Source digest: `github-growth-20260707T190110.064980Z`
- Capability slice: skill-route-discovery
- Rollback artifact: `artifacts/rollback/20260707T190108Z-skill-route-discovery-pass2/rollback-point.md`
- Rollback ref: `refs/rollback/20260707T190108Z-skill-route-discovery-pass2`
- Self-model decision: unchanged; the existing preference for rollback-backed local validation already matches this run.

## Evidence Review

- `lingbol088-spec/reverse-flow-skill` is treated as Codex workflow-gate skill evidence because the public repository exposes a `skills/reverse-flow` shape, `SKILL.md` workflow framing, local sandbox/CTF boundaries, and diagnostic script examples.
- `Pluviobyte/rnskill` is treated as a generic `SKILL.md` collection because the public repository exposes `skills/`, docs, tools, marketplace-style metadata, and manual install examples for Codex/Claude-compatible skills.
- `shepherd-agents/shepherd` and PR #18 are treated as adjacent agent-harness evidence because they describe or touch a reversible agent runtime substrate, not a local skill route.

## Local Change

- Added `github-growth-20260707T190110.064980Z` to the pass-2 skill-route dispatcher.
- Added a pass-2 operator validation lane label, proposal IDs, rollback metadata, and adjacent-agent handoff for the current digest.
- Added a body-free fixture and regression test proving reverse-flow and rnskill stay in bounded skill-route lanes while Shepherd, Agents-A1, Fundamental-Ava, and Shepherd PR activity remain behind agent-harness evaluation.
- Updated `docs/skill-route-discovery.md` with the current digest replay contract.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T190110`

## Review Notes

- No upstream repository was cloned, installed, or executed.
- No external skill activation, external harness execution, provider launch, remote execution, memory write, profile write, restart, promotion, or push was performed.
- Raw source URLs and replay commands are accepted in fixture input but must not appear in controller output; the regression checks this.
