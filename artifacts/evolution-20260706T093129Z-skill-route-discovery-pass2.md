# Skill Route Discovery Pass 2

Source digest: `github-growth-20260706T093129.770380Z`

Hypothesis: the active mixed evidence window should be replayable as a bounded
local validation lane before activation. `lingbol088-spec/reverse-flow-skill`
may enter `skill_route_discovery`, but adjacent general-agent projects must
remain behind `agent_harness_eval_required` until a local harness result exists.

Rollback point:

- Branch: `codex/blackhole-evolve/20260706T093219.739540-add-or-run-a-bounded-skill-route-discovery-valid`
- HEAD: `f0c8748d196bdbb7373f6b35619180dffbf807a7`
- Ref: `refs/blackhole-rollback/20260706T093128Z`
- Artifact: `artifacts/rollback/20260706T093128Z.rollback.txt`

Material actions:

- Reviewed `docs/self-model.md`; left it unchanged because it already states
  the current rollback-backed local evolution and narrow safety boundary.
- Added a 09:31 pass-2 route-discovery fixture for reverse-flow-skill plus the
  four adjacent general-agent projects.
- Added a regression that validates the pass-2 lane map and route packet, with
  selected evidence refs constrained to fixture `item_id` values and no raw
  GitHub URLs or runtime/provider/install lanes exported.
- Updated `docs/skill-route-discovery.md` with the replay command and route
  split for this digest.

Review notes:

- External evidence was used only as focused route-shape context. No upstream
  code was cloned, installed, imported, or executed.
- Activation remains delegated to the external supervisor after local
  validation.

Validation:

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T093129`
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T060238 or 20260706T093129"`
- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or 20260706T091129"`
- `python -m pytest tests/test_skill_routing.py -q`
- `python -m pytest tests/test_docs_contracts.py -q`
