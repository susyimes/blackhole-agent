# Blackhole Run: skill-route-discovery pass 4 completion

- Source digest: `github-growth-20260706T143556.012746Z`
- Branch: `codex/blackhole-evolve/20260706T143701.921178-add-or-exercise-a-local-skill-route-discovery-va`
- Rollback artifact: `artifacts/rollback/20260706T143554Z-skill-route-discovery-pass4-current-window/rollback-point.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T143554Z-skill-route-discovery-pass4-current-window`
- Self-model: read and left unchanged. The current text already describes rollback-backed, locally validated evolution and keeps permissions external; this run had stronger evidence for an operator-visible route handoff.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted as Codex/AI Agent skill workflow evidence only. The useful local lesson is the bounded skill-route lane, not installing or running the upstream skill.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/shepherd-agents/shepherd`, and `https://github.com/shepherd-agents/shepherd/pull/24`: interpreted as general-agent project and runtime-substrate evidence requiring local harness evaluation before any implementation lane.

## Hypothesis

The final pass of this skill-route-discovery window should expose a replayable pass-4 completion handoff for the current digest. Reverse-flow skill evidence can close through bounded local documentation/config/test/code_patch lanes, while adjacent general-agent projects remain `agent_harness_eval_required` with no direct implementation, runtime, provider, external harness, or remote-execution route.

## Change

- Added `github-growth-20260706T143556.012746Z` to the existing 20260706 pass-4 completion handoff path.
- Added a frozen route fixture for the current digest and a focused regression test that checks proposal IDs, bounded lanes, agent-harness gating, and body-free output.
- Documented the current digest replay path in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T143556`

## Review Notes

- No upstream code was installed, executed, or imported.
- Raw evidence URLs are present only in input fixtures; the asserted handoff output keeps raw source URLs, replay commands, target paths, and upstream bodies unexported.
- General-agent projects remain blocked behind local harness evaluation before documentation, test, or code_patch follow-up.
