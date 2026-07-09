# Skill Route Discovery Pass 1

- Source digest: `github-growth-20260709T101527.212913Z`
- Branch: `codex/blackhole-evolve/20260709T101602.763288-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback ref: `refs/blackhole/rollback/20260709T101525Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260709T101525Z-skill-route-discovery-pass1/rollback-point.md`

## Hypothesis

External SKILL.md-style repositories should become bounded local route evidence,
not runtime activation authority. For the current window, `reverse-flow-skill`
should validate the local test lane, `rnskill` should validate the documentation
lane, and adjacent agent/workflow projects should queue behind
`agent_harness_eval` before documentation, test, or code_patch follow-up.

## Evidence Reviewed

- `https://github.com/Pluviobyte/rnskill`: public AI Agent Skills collection
  with `SKILL.md`-compatible skills, docs, tools, and plugin/marketplace shape.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI
  Agent reverse-flow skill workflow with local sandbox framing and staged
  workflow language.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`:
  public workflow-usecase collection, treated as adjacent harness-eval evidence.
- `https://github.com/SmileLikeYe/agent-chief`: public local-first agent
  orchestration project, treated as adjacent harness-eval evidence.

No external repository code was fetched, cloned, installed, or executed.

## Local Change

- Added `current_digest_20260709T101527_pass1_local_skill_route_discovery` to
  the skill-route lane map.
- Added a regression fixture that asserts `skill_route_discovery` maps only to
  documentation, config, test, or code_patch lanes and that adjacent projects
  require `agent_harness_eval` before follow-up work.
- Updated the route-discovery documentation with the pass-1 operator surface and
  replay command.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already
matches this run: local evolution is allowed when rollback-backed and locally
validated, while runtime execution and privacy/offensive routes remain bounded
by external policy.

## Validation

Passed:

```bash
python -m pytest tests/test_skill_routing.py -q -k 20260709T101527
# 1 passed, 462 deselected

python -m pytest tests/test_skill_routing.py -q -k "20260709T101527 or 20260709T095527 or 20260709T091527"
# 3 passed, 460 deselected
```
