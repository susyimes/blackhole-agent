# Skill Route Discovery Pass 2

- Source digest: `github-growth-20260702T074714.911556Z`
- Capability slice: convert skill and route evidence into bounded local lanes that can be validated before activation.
- Rollback artifact: `artifacts/self-evolution/github-growth-20260702T074714Z-rollback.md`

## Hypothesis

The current pass-2 evidence should be operator-visible as a local validation lane: zhengxi-views and BioNeMo Agent Toolkit are skill/workflow route evidence bounded to documentation, config, test, or code_patch, while Qwen-AgentWorld and Fundamental-Ava remain behind `agent_harness_eval_required`.

## Changes

- Added digest recognition for `github-growth-20260702T074714.911556Z` in `current_digest_pass2_local_validation_lane`.
- Added a frozen body-free fixture for the current digest.
- Added a focused regression for bounded skill lanes, downgraded unsupported lane pressure, and adjacent general-agent gating.
- Updated `docs/skill-route-discovery.md` with the pass-2 interpretation.

## External Evidence Review

- `https://github.com/lyra81604/zhengxi-views`: public repository exposes `SKILL.md`, `skill.yml`, references, scripts, evals, source-citation framing, and a non-investment-advice boundary.
- `https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit`: public repository advertises agent skills and skill/workflow catalog signals.
- `https://github.com/QwenLM/Qwen-AgentWorld`: public general-agent benchmark/project evidence without local skill workflow route hints in this pass.
- `https://github.com/TianhangZhuzth/Fundamental-Ava`: public autonomous/collaborative agent evidence without local skill workflow route hints in this pass.

## Review Notes

- No upstream repository was cloned, installed, imported, or executed.
- No raw upstream bodies, replay commands, target paths, private data, or credentials were exported.
- The self-model was read and left unchanged; its current preference already matches this run's local-validation-first behavior.
