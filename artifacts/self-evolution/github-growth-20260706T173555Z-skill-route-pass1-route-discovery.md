# Evolution Run: skill-route-discovery pass 1 route discovery

- Source digest: `github-growth-20260706T173555.511473Z`
- Branch: `codex/blackhole-evolve/20260706T173654.359177-create-or-extend-a-local-agent-harness-evaluatio`
- Rollback artifact: `artifacts/rollback-20260706T173555Z-skill-route-discovery-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260706T173555Z-skill-route-discovery-pass1`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: approved external evidence only. The public page shows a `skills/reverse-flow` skill package shape, `SKILL.md`, references, scripts, an `agents/openai.yaml` route, local sandbox and CTF/crackme/training framing, staged reverse-analysis workflow, and install/run examples.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/shepherd-agents/shepherd`: carried as general-agent project evidence from the digest window. They are not treated as skill-route evidence.

## Hypothesis

The next pass should be operator-visible before activation: reverse-flow-skill can map to a bounded local documentation lane for candidate integration points, tests, and rollback expectations, while general-agent projects must enter `agent_harness_eval_required` before runtime, runner, scheduling, memory, tool-routing, documentation, test, or code_patch follow-up.

## Change

- Added `current_digest_20260706T173555_pass1_validation_lane.json` as a frozen body-free fixture.
- Extended pass-1 skill-route dispatch for `github-growth-20260706T173555.511473Z`.
- Added a regression test asserting the reverse-flow row is bounded to allowed lanes and all general-agent rows remain harness-gated.
- Updated `docs/skill-route-discovery.md` with the current pass rule.

## Review Notes

- Proposal `p1-agent-harness-eval-general-projects` remains review-only for behavior adoption; the local output only records `agent_harness_eval_required` rows.
- No upstream skill code was installed, copied, executed, activated, or imported.
- No provider, external harness, remote execution, profile write, memory write, push, promotion, restart, raw source URL export, replay-command export, or upstream body export was added.
- Reverse-engineering and vulnerability-analysis wording is treated as route pressure only. Offensive behavior, abuse, unauthorized access, and privacy leakage remain outside local activation.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T173555`: passed, 1 test.
- `python -m ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 345 tests.
