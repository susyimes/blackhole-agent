# Skill Route Discovery Pass 3 Current Digest

- source_digest: `github-growth-20260630T104714.619738Z`
- rollback_artifact: `artifacts/rollback-20260630T184837Z.md`
- rollback_ref: `refs/blackhole-agent/rollback/20260630T184837Z`
- branch: `codex/blackhole-evolve/20260630T104807.560306-run-a-bounded-skill-route-discovery-validation-f`

## Evidence

- `https://github.com/lyra81604/zhengxi-views` was treated as `skill_route_discovery` evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/ksimback/looper` were treated as adjacent `agent_harness_eval_required` evidence.
- No broad trend discovery was rerun.

## Hypothesis

The active pass-3 wake needs an operator-visible activation-review lane for its exact digest, not only earlier pass-3 fixtures. A bounded local lane should keep the zhengxi-views skill-route proposal separate from the Qwen-AgentWorld and looper harness-eval proposals, strip unsupported runtime/install/provider lanes from exported activation-review output, and keep all runtime or external activation authority denied.

## Change

- Added a frozen current-digest fixture for `github-growth-20260630T104714.619738Z`.
- Updated `skill_route_discovery_current_digest_pass3_activation_review_lane` to recognize this digest and preserve separate adjacent harness-eval rows for Qwen-AgentWorld and looper.
- Added regression coverage that checks bounded local lanes, separate proposal IDs, no raw URLs or replay commands, no runtime/install/provider lane export, and denied external activation.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: reversible local evolution is preferred when rollback-backed and validated, while runtime execution, provider launch, upstream skill activation, and privacy-sensitive export remain outside this bounded lane.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260630T104714 or 20260630T092714_pass3 or current_digest_20260630T094714_pass4"`: passed, 3 tests.
- `PYTHONPATH=src python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane`: passed, 3 tests.
- `python -m py_compile src/blackhole_agent/skill_routing.py`: passed.

An initial pytest attempt without `PYTHONPATH=src` imported a sibling checkout at `C:\Users\svmes\Documents\Playground\blackhole-agent`; validation above pins imports to this worktree.
