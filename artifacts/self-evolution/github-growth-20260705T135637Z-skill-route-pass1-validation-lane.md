# Skill Route Discovery Pass 1 Validation Lane

Source digest: github-growth-20260705T135637.037461Z

## Hypothesis

The current pass-1 window should expose a bounded local validation lane before
activation: reverse-flow-skill is skill-route evidence, while general agent
projects and workflow-only repository signals remain behind local
agent-harness evaluation.

## Evidence Interpreted

- https://github.com/lingbol088-spec/reverse-flow-skill: public Codex/AI Agent
  skill workflow shape with `skills/reverse-flow`, `SKILL.md`, references,
  scripts, local sandbox/CTF framing, install examples, and staged workflow
  language.
- https://github.com/InternScience/Agents-A1,
  https://github.com/QwenLM/Qwen-AgentWorld, and
  https://github.com/TianhangZhuzth/Fundamental-Ava: general agent-project
  signals without explicit local skill-route hints or local harness results.
- https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases:
  workflow-topic evidence only; it remains an agent-harness candidate, not a
  direct workflow-routing change.

## Change

- Registered `github-growth-20260705T135637.037461Z` in the pass-1
  current-digest dispatcher.
- Added a frozen current-digest fixture and regression that checks:
  - reverse-flow selects the bounded local `test` lane first;
  - general agent projects use `agent_harness_eval_required`;
  - workflow-only Seedance evidence is documented as a harness-gated lane;
  - no raw upstream URLs, replay commands, target paths, upstream bodies,
    provider launch, external harness execution, runtime execution, or remote
    execution are exported or enabled.

## Rollback

- Ref: `refs/blackhole/rollback/20260705T135637Z-skill-route-discovery-pass1`
- Artifact:
  `artifacts/rollback/20260705T135637Z-skill-route-discovery-pass1/rollback-point.md`

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260705T135637`
  - Result: 1 passed, 305 deselected.
- `python -m pytest tests/test_skill_routing.py -q -k "20260705T135637 or 20260705T122958"`
  - Result: 2 passed, 304 deselected.

## Review Notes

- Self-model left unchanged: the existing preference for rollback-backed,
  locally validated behavior changes already matches this run.
- No upstream code was cloned, installed, executed, or activated.
- No restart, push, promotion, provider launch, profile write, or memory write
  was performed by this kernel.
