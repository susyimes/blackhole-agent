# Skill Route Discovery Pass 2 Operator Manifest

Source digest: github-growth-20260629T004729.561444Z

Branch: codex/blackhole-evolve/20260629T004813.900440-add-or-extend-local-tests-for-skill-route-discov

Rollback point:

- Ref: refs/rollback/blackhole-agent-20260629T004728Z
- Artifact: artifacts/rollback/blackhole-agent-20260629T004728Z.txt
- Head: eb2e40a76759d29b5671720c2c9af5619f5967a9

Hypothesis:

Pass-2 skill-route discovery already has candidate lane tests, but operators need a compact
pre-activation manifest that ties selected and queued bounded lanes to route profiles, local artifact
proofs, replay commands, and denied runtime actions. This improves the active skill-route-discovery
slice without executing upstream skill code or external harnesses.

Evidence reviewed:

- https://github.com/dongshuyan/compass-skills
- https://github.com/lyra81604/zhengxi-views

Reusable lesson:

Skill ecosystem and generic skill repositories should be converted into local validation work only:
documentation/config/test/code_patch lanes, selected evidence IDs or hashes, local artifact review,
and explicit denial of external activation until local replay succeeds.

Changed files:

- src/blackhole_agent/harness_eval.py
- tests/test_harness_eval.py

Validation:

- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff"`: passed
- `python -m pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`: passed

Review notes:

- docs/self-model.md was read and left unchanged. Its preference for rollback-backed, locally
  validated behavior changes fits this run; no new self-description evidence required an edit.
- No runtime restart, provider launch, remote execution, upstream clone/run, or external skill
  activation was performed.
