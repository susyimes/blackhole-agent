# Evolution Run: skill-route-discovery pass 1 current digest lane

## Rollback

- Original branch: `codex/blackhole-evolve/20260703T052159.534176-add-or-extend-local-tests-for-skill-route-discov`
- Original HEAD: `fb07094a22a3f4807a514ad733a596c15b07ce6a`
- Rollback ref: `refs/blackhole/rollback/20260703T052048Z`
- Recovery commands:
  - `git reset --hard refs/blackhole/rollback/20260703T052048Z`
  - `git clean -fd`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted from the carried digest as Codex workflow skill-route evidence with unsupported `provider_runtime` and `runtime_execution` suggestions.
- `https://github.com/lyra81604/zhengxi-views`: interpreted from the carried digest as source-cited skill-route metadata evidence.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`, `https://github.com/QwenLM/Qwen-AgentWorld`, and `https://github.com/TianhangZhuzth/Fundamental-Ava`: interpreted as adjacent workflow or general-agent evidence that requires `agent_harness_eval_required` before implementation or runtime behavior.

## Hypothesis

The active pass-1 slice should expose an operator-visible lane for `github-growth-20260703T052050.251723Z`. Skill-route evidence can be validated in bounded documentation, config, test, or code_patch lanes, while unsupported provider/runtime suggestions remain visible only as downgraded lane pressure. Adjacent workflow and general-agent items must stay behind local harness evaluation.

## Change

- Added a digest-specific pass-1 route lane for `github-growth-20260703T052050.251723Z`.
- Added a current digest fixture that carries reverse-flow-skill, zhengxi-views, Seedance workflow usecases, Qwen-AgentWorld, and Fundamental-Ava.
- Added regression coverage for bounded skill-route lanes, Codex workflow gate ordering, downgraded unsupported lane pressure, adjacent harness-eval gating, and body-free output.

## Validation

- `PYTHONPATH=src python -m pytest tests/test_skill_routing.py -q -k "20260703T052050 or 20260703T040049"`: passed.

## Review Notes

- `docs/self-model.md` was read and left unchanged; this run had a concrete behavior/test improvement, and the existing self-model already matched the rollback-backed local-evolution posture.
- Validation must set `PYTHONPATH=src` in this worktree because the ambient Python environment imports another editable checkout when `PYTHONPATH` is not set.
