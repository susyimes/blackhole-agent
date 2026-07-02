# Skill Route Discovery Pass 1

Source digest: `github-growth-20260702T152626.587436Z`

Rollback point:
`artifacts/rollback-20260702T152626Z-skill-route-discovery-pass1.md`

## Evidence Review

- `https://github.com/lyra81604/zhengxi-views` was treated as public Agent Skill
  route evidence. The reusable pattern is the package shape: `SKILL.md`,
  `skill.yml`, references, evals, scripts, source-citation workflow boundaries,
  and non-investment-advice limits.
- `https://github.com/QwenLM/Qwen-AgentWorld` and
  `https://github.com/Leo0186/qwen-agentworld` were treated as one
  general-agent evaluation lane with fork corroboration, not separate local
  implementation targets.
- `https://github.com/TianhangZhuzth/Fundamental-Ava` remained a general-agent
  project signal requiring an evaluation checklist before any implementation
  route.

## Local Change

Added a digest-specific pass-1 branch for
`github-growth-20260702T152626.587436Z` in `skill_routing.py`.

Added a frozen fixture and regression test that verify:

- zhengxi-views maps to `skill_route_discovery` and only the bounded local lane
  envelope: documentation, config, test, code_patch.
- Qwen-AgentWorld and Fundamental-Ava stay in `agent_harness_eval_required`.
- The Qwen fork is carried as duplicate ecosystem evidence in the anchoring
  proposal IDs, not as an extra implementation row.
- Fundamental-Ava contributes a documentation checklist lane for runnable
  surface, configuration assumptions, tool routing, rollback, and non-network
  validation.

## Validation

Passed:

- `pytest tests/test_skill_routing.py -q` -> 175 passed
- `pytest tests/test_docs_contracts.py -q` -> 11 passed

## Review Notes

No offensive behavior, unauthorized access, or privacy-leakage route was
selected. No upstream code was cloned, installed, imported, or executed. The
self-model was read and left unchanged because it already matched the
validated-local-lane behavior used in this run.
