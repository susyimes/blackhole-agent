# Skill Route Discovery Pass 3 Current Window

Source digest: `github-growth-20260703T201923.796362Z`

Hypothesis: the active pass-3 skill-route-discovery slice should have an
operator-visible route-to-validation lane for the current digest before any
workflow routing or general-agent adoption can be considered.

Evidence reviewed:

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI
  Agent reverse-flow skill package with `skills/reverse-flow`, local sandbox and
  CTF workflow framing, scripts, and install/runtime wording that must stay
  downgraded until local validation.
- `https://github.com/lyra81604/zhengxi-views`: public Agent Skill repository
  with `SKILL.md`, `skill.yml`, references, evals, scripts, source-cited
  workflow language, and non-investment-advice boundary metadata.
- `https://github.com/Forsy-AI/agent-apprenticeship`: general agent workflow
  loop and mentor-evaluation project; it is not a direct skill-route candidate
  without local harness evaluation.

Change applied:

- Added `github-growth-20260703T201923.796362Z` handling to
  `current_digest_pass3_route_to_validation_lane`.
- Added a frozen current-digest fixture and regression test for the pass-3
  route lane.
- Documented the current pass-3 lane and replay command.

Self-model decision: left unchanged. The current self-model already says to
prefer rollback-backed, locally validated behavior changes over report-only
work, and this run followed that rule without needing new self-description.

Rollback:

- Ref: `refs/rollback/blackhole-agent/20260703T201923-skill-route-discovery-pass3`
- Artifact:
  `artifacts/rollback/20260703T201923Z-skill-route-discovery-pass3-current-window/rollback-point.md`

Validation:

- Passed: `python -m pytest tests/test_skill_routing.py -q -k 20260703T201923`
- Passed: `python -m pytest tests/test_skill_routing.py -q`
- Passed: `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery`
