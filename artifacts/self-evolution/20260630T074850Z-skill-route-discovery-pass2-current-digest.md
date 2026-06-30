# Self-Evolution Run: Skill Route Discovery Pass 2

Source digest: `github-growth-20260630T074714.730934Z`

Capability slice: `skill-route-discovery`

Hypothesis:

Current zhengxi-views skill evidence should produce bounded local validation
lanes that are visible to the operator before activation, while adjacent
general-agent projects remain behind `agent_harness_eval` and security-adjacent
automation evidence remains review-only.

Evidence reviewed:

- `https://github.com/lyra81604/zhengxi-views`
- Frozen digest proposal IDs and evidence URLs from the current wake.
- Existing pass-1/pass-2 local fixtures and route interpretation docs.

Rollback:

- Artifact: `artifacts/rollback/20260630T074850Z-skill-route-discovery-pass2.md`
- Ref: `refs/blackhole-rollback/20260630T074850Z-skill-route-discovery-pass2`

Changes:

- Added a digest-specific pass-2 route in `src/blackhole_agent/skill_routing.py`.
- Added frozen digest fixture coverage for `github-growth-20260630T074714.730934Z`.
- Added a focused regression test asserting bounded skill lanes, adjacent
  harness-eval requirements, review-only open-reverselab handling, and
  body-free operator replay output.
- Documented the current pass-2 route-hint interpretation.

Self-model decision:

`docs/self-model.md` was left unchanged. The current self-model already states
the relevant autonomy boundary; this run produced behavior evidence, not a
new self-description requirement.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260630T074714`
- `python -m compileall -q src\blackhole_agent`
- `python -m pytest tests/test_skill_routing.py -q`

Review notes:

- open-reverselab remains review-only at the offensive-behavior boundary.
- The lane exports hashes and body-free metadata only; raw URLs and replay
  commands are not exported from the route packet.
- No restart, provider launch, external harness execution, profile write,
  memory write, remote execution, push, or promotion was performed.
