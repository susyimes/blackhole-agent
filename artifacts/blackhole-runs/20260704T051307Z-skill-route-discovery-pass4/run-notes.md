# Blackhole Run: skill-route-discovery pass 4

Source digest: `github-growth-20260704T051308.904452Z`

Branch: `codex/blackhole-evolve/20260704T051405.051000-run-bounded-skill-route-discovery-for-the-codex-`

Rollback ref: `refs/blackhole-rollback/20260704T051307Z-skill-route-discovery-pass4`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill package with `skills/reverse-flow`, a trigger phrase, local CTF/sandbox framing, scripts, and install/runtime pressure.
- `https://github.com/lyra81604/zhengxi-views`: public source-cited Agent Skill with skill metadata, references/evals, and an explicit research-only/advice boundary.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent benchmark/world-model project with eval assets, not a skill package.

## Hypothesis

Pass 4 should finish this capability slice with a supervisor-visible recovery workflow, not another standalone fixture. The current evidence supports a bounded local completion handoff: reverse-flow stays discovery-first in the local test lane, zhengxi-views stays in the documentation lane, and general-agent projects remain behind local agent-harness evaluation.

## Changes

- Created rollback ref and rollback artifact.
- Added a current-digest pass-4 fixture for `github-growth-20260704T051308.904452Z`.
- Wired the digest into the existing reverse-flow/Codex pass-4 completion handoff.
- Added `operator_recovery_workflow` to the generated handoff with rollback, focused-validation, supervisor-record-only, and no-kernel-restart gates.
- Added a focused regression test for the current pass-4 handoff.
- Documented the current digest in `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged; it already supports rollback-backed local behavior changes and did not need a new behavior-shaping claim for this run.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260704T051308`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260704T051308 or 20260704T043308 or 20260704T035308"`: passed, 3 tests.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 247 tests.

## Review Notes

The handoff remains metadata-only. It exports proposal IDs, lane names, selected item IDs, hashes, and denial booleans; it does not export raw source URLs, raw replay commands, upstream bodies, target paths, provider inputs, runtime authority, or activation authority. Restart, promotion, push, and activation remain external supervisor responsibilities.
