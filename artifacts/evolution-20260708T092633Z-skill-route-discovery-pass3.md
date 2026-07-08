# Evolution Run: skill-route-discovery pass 3 proposal replay lane

- Source digest: `github-growth-20260708T092635.428641Z`
- Branch: `codex/blackhole-evolve/20260708T092730.105783-add-or-update-a-local-skill-route-discovery-note`
- Rollback artifact: `artifacts/rollback-20260708T092633Z-skill-route-discovery-pass3.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260708T092633Z-skill-route-discovery-pass3`
- Self-model: unchanged

## Hypothesis

The pass-3 skill-route-discovery window should expose an operator-visible replay
plan keyed to the current proposals before pass 4. Skill/workflow evidence can
advance only through documentation or test lanes here, while general-agent
project evidence remains behind `agent_harness_eval_required` with no direct
implementation or runtime action.

## Evidence Interpretation

- `lingbol088-spec/reverse-flow-skill`: carried as Codex workflow-gate
  skill-route evidence for bounded local test validation.
- `Pluviobyte/rnskill`: carried as generic `SKILL.md` workflow evidence for a
  bounded documentation lane.
- `shepherd-agents/shepherd`, `Tencent-Hunyuan/Hy3`, and workflow-usecase
  evidence: carried as adjacent general-agent or workflow pressure requiring
  local agent-harness evaluation before any follow-up lane.

No new upstream evidence was fetched during this interpretation layer.

## Changes

- Added `skill_route_discovery_current_digest_20260708T092635_pass3_proposal_replay_lane`.
- Added `proposal_replay_plan` rows for:
  - `p1-skill-route-discovery-catalog`: documentation lane.
  - `p2-skill-route-discovery-tests`: test lane.
  - `p3-agent-harness-eval-probe`: `agent_harness_eval_required`.
- Added a current digest fixture and regression coverage.
- Documented the replay lane in `docs/skill-route-discovery.md`.

## Validation

- `python -m py_compile src\blackhole_agent\skill_routing.py`: passed.
- `python -m pytest tests\test_skill_routing.py -q -k 20260708T092635`: passed, 1 test.
- `python -m pytest tests\test_skill_routing.py -q -k "20260708T090635 or 20260708T092635"`: passed, 2 tests.
- `python -m pytest tests\test_skill_routing.py tests\test_docs_contracts.py -q -k "20260708T092635 or 20260708T090635"`: passed, 3 tests.

## Review Notes

- The lane is body-free and exports no raw source URLs, evidence URLs, replay
  commands, target paths, or upstream bodies.
- Runtime action, external skill activation, external agent activation,
  external harness execution, provider launch, profile writes, memory writes,
  remote execution, push, promotion, restart, and activation remain disabled.
