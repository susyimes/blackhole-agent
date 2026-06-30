# Skill Route Discovery Pass 4 Agent-Harness Readiness

Source digest: `github-growth-20260630T110714.560687Z`
Branch: `codex/blackhole-evolve/20260630T110820.182936-run-a-bounded-local-skill-route-discovery-evalua`
Rollback artifact: `artifacts/rollback-20260630T110713Z-skill-route-discovery-pass4-agent-harness-readiness.md`

## Evidence

- `https://github.com/lyra81604/zhengxi-views`: treated as the carried skill-route signal for bounded documentation/config/test/code_patch lanes.
- `https://github.com/QwenLM/Qwen-AgentWorld`: treated as adjacent general-agent evaluation evidence, not skill-route inheritance.
- `https://github.com/ksimback/looper`: treated as adjacent general-agent loop/controller evidence, not direct runtime or external harness authority.

## Hypothesis

The pass-4 completion surface should not stop at saying that Qwen-AgentWorld and
looper require `agent_harness_eval`. It should expose a local, body-free
project completion matrix that tells the supervisor when each adjacent project
has enough intake metadata, mapped local capability claims, bounded lanes, and
passed replay criteria before any documentation, test, or code_patch follow-up
is allowed.

## Changed Files

- `src/blackhole_agent/harness_eval.py`: adds
  `agent_harness_eval_project_completion_matrix` inside the implementation
  readiness contract.
- `tests/fixtures/local_harness_eval/agent_harness_eval_lane_qwen_looper_readiness.json`:
  adds a bounded replay fixture for the current Qwen-AgentWorld and looper
  readiness path.
- `tests/test_harness_eval.py`: updates aggregate local harness fixture counts
  and checks the new fixture passes.
- `docs/skill-route-discovery.md`: records the pass-4 operator-visible behavior.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or local_harness_eval_runs_pass"`: passed.
- `python -m pytest tests/test_skill_routing.py -q -k "20260630T104714 or 20260630T094714 or source_cited_domain_research"`: passed.

## Review Notes

- The self-model was read and left unchanged; it already supports locally
  validated evolution without acting as a permission source.
- The matrix remains metadata-only and denies external harness execution,
  provider launch, remote execution, profile writes, memory writes, raw source
  URL export, and upstream body export.
- No restart, push, promotion, or external activation was performed by this
  kernel run.
