# Skill Route Discovery Pass 4 Current Window

Source digest: `github-growth-20260708T161850.608560Z`

Hypothesis: the final pass of the reverse-flow/rnskill/Shepherd window should
complete through an operator-visible handoff rather than another standalone
fixture. Codex-oriented skill workflow evidence should remain in the bounded
local test lane, generic skill-workflow evidence should remain in the
documentation lane, and general-agent/runtime evidence should stay behind
`agent_harness_eval_required` with `runtime_action` set to `none`.

Evidence reviewed:

- `lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill repository
  with `skills/`, `SKILL.md`, local sandbox/CTF framing, workflow steps, install
  examples, and scripts. Install/run/runtime wording is route pressure only.
- `Pluviobyte/rnskill`: generic AI Agent Skills collection, treated as
  documentation-first generic skill workflow evidence.
- `shepherd-agents/shepherd`: general agent runtime substrate evidence,
  retained as adjacent harness-eval material before any implementation lane.

Changed behavior:

- Added `current_digest_20260708T161850_pass4_operator_handoff` to the skill
  route lane map.
- The handoff reports the current proposal IDs, rollback artifact, bounded
  local lanes, activation denials, and adjacent general-agent holdback rows.
- No external skill activation, install, provider launch, external harness
  execution, remote execution, promotion, restart, profile write, memory write,
  raw URL export, raw replay command export, target-path export, or upstream
  body export was added.

Self-model: left unchanged. It already states the local preference used here:
validated rollback-backed behavior changes over ornamental reports, with
external permissions remaining outside the file.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260708T161850`: passed, 1 passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260708T145852 or 20260708T161850"`: passed, 2 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 18 passed.
- `ruff check src/blackhole_agent/skill_routing.py tests/test_skill_routing.py`: passed.
