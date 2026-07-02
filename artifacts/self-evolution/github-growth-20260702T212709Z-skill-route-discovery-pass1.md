# Skill Route Discovery Pass 1

- Source digest: github-growth-20260702T212709.490066Z
- Capability slice: skill-route-discovery
- Rollback artifact: artifacts/self-evolution/github-growth-20260702T212709Z-rollback.md
- Rollback ref: refs/rollback/github-growth-20260702T212709Z

## Evidence Reviewed

- https://github.com/lyra81604/zhengxi-views
- https://github.com/QwenLM/Qwen-AgentWorld
- https://github.com/TianhangZhuzth/Fundamental-Ava
- https://github.com/ksimback/looper

The zhengxi-views repository exposes public Agent Skill shape through SKILL.md,
skill.yml, references, evals, scripts, source-cited research boundaries, and a
non-investment-advice limit. Qwen-AgentWorld, Fundamental-Ava, and looper are
general agent or agent-loop projects without a skill-route hint in this digest.
The workflow-usecase item is workflow-keyword evidence without SKILL.md or a
recognized local workflow-route signal.

## Hypothesis

The pass-1 route surface should bind the active skill-route-discovery proposal
IDs to an operator-visible validation lane. Skill-shaped evidence may enter only
bounded local documentation/config/test/code_patch lanes, while general-agent
and workflow-keyword-only trends remain behind agent_harness_eval_required
until local harness validation supplies stronger implementation evidence.

## Local Change

- Added a current digest pass-1 specialization for
  github-growth-20260702T212709.490066Z.
- Added `workflow_topic_boundary` to the pass-1 controller surface so
  workflow-keyword-only evidence is visible as an agent-harness gate with no
  direct local lanes before evaluation.
- Added a frozen fixture and regression test for the active proposal set.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260702T212709 or 20260702T210709"
python -m pytest tests/test_skill_routing.py -q
```

Result: both commands passed.

## Review Notes

- No external skill activation, provider runtime launch, remote execution, or
  external harness execution was enabled.
- Raw GitHub URLs and replay commands remain absent from the serialized
  controller surface.
- Self-model was left unchanged because this run produced a concrete route
  behavior improvement and the existing self-model already matches the
  rollback-backed local validation posture.
