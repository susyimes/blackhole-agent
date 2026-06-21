# Skill Route Discovery Pass 3 Final Replay Checklist

Source digest: `github-growth-20260621T035207.832344Z`

Rollback point:
`artifacts/rollback/20260621T035207Z-skill-route-discovery-pass3.txt`

Hypothesis: pass-3 skill-route discovery already classifies COMPASS,
Three.js Game Skills, and FableCodex evidence into bounded local lanes, but the
handoff benefits from a supervisor-visible final-pass replay checklist. The
checklist should make the selected `test` lane, queued `config` lane, secondary
harness block, and body-free export checks explicit without adding activation
authority.

Evidence reviewed:

- `https://github.com/dongshuyan/compass-skills` describes local agent skills
  for task clarification, repo-local task memory, handoff prompts, and a local
  collaboration profile.
- `https://github.com/majidmanzarpour/threejs-game-skills` describes a Three.js
  game director workflow with bundled scaffold/helper materials and QA checks.
- `https://github.com/baskduf/FableCodex` describes Codex workflow gates,
  ledgers, examples, tests/evals, and verification habits.

Change:

- Added `final_pass_replay_checklist` to `pass3_handoff_packet`.
- The checklist has four metadata-only steps:
  `replay_selected_current_pass_lane`, `carry_queued_bounded_lanes`,
  `preserve_secondary_harness_block`, and `verify_body_free_final_handoff`.
- Updated the pass-3 regression and route discovery documentation.

Validation:

- `pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`
- `pytest tests/test_skill_routing.py -q`
- `pytest tests/test_docs_contracts.py -q`
- `pytest tests/test_harness_eval.py -q`

Review notes:

- Self-model was read and left unchanged. It already matches this run's local
  validated evolution preference and does not grant permissions.
- The change is body-free metadata only. It does not install, enable, run, or
  import upstream skill repositories, execute external harnesses, launch
  providers, perform remote execution, export raw evidence URLs, or expose
  upstream bodies.
