# Skill Route Discovery Pass 3 Run Note

Source digest: `github-growth-20260702T003748.734027Z`

Rollback point: `artifacts/rollback-20260702T003747Z-skill-route-discovery-pass3.md`

Hypothesis: the active pass-3 route-to-validation surface should preserve the
current proposal IDs instead of falling back to generic IDs, while keeping
skill-route evidence bounded to local documentation/config/test/code_patch lanes
and keeping general-agent evidence in `agent_harness_eval_required`.

Evidence reviewed:

- `https://github.com/lyra81604/zhengxi-views`: public repository page showed
  `SKILL.md`, `skill.yml`, `references/`, `scripts/`, `evals/`, source-cited
  research framing, and non-investment-advice boundary language.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public repository page reviewed
  as general-agent project context.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public repository page
  reviewed as general-agent project context.

Local actions:

- Created rollback ref
  `refs/blackhole-rollback/20260702T003747Z-skill-route-discovery-pass3`.
- Extended `skill_route_discovery_current_digest_pass3_route_to_validation_lane`
  to recognize `github-growth-20260702T003748.734027Z`.
- Added frozen current-digest fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260702T003748_pass3_route_to_validation.json`.
- Added focused test coverage for current proposal IDs, bounded skill-route
  lanes, hashed replay commands, and general-agent harness gating.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k "current_20260702_pass3 or current_digest_pass3_routes_to_validation"`:
  passed, 2 passed and 146 deselected.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 148 passed.
- `python -m pytest tests/test_proposal_eval.py -q -k skill_route_discovery`:
  passed, 4 passed and 21 deselected.

Review notes:

- Self-model was read and left unchanged; it already states the current run's
  preference for rollback-backed local behavior changes and narrow safety
  boundaries.
- No runtime activation, provider launch, external harness execution, remote
  execution, profile write, memory write, or upstream body export was added.

