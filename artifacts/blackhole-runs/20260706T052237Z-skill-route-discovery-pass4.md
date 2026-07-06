# Skill Route Discovery Pass 4

Source digest: `github-growth-20260706T052238.803216Z`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill package shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox/CTF framing, install examples, and staged reverse workflow language.
- `https://github.com/zhenluwang23-sys/reverse-flow-skill`: fork-lineage reverse-flow skill evidence with the same public skill package shape.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/QwenLM/Qwen-AgentWorld`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/shepherd-agents/shepherd`: general-agent or runtime/workflow project evidence without a local skill-route hint or bounded local harness result.

## Hypothesis

The final pass for the active skill-route window should expose an operator-visible completion handoff for the current digest: reverse-flow skill evidence may enter only documentation, config, test, or code_patch validation lanes, while general-agent evidence remains `agent_harness_eval_required` with no direct implementation lane before local harness evaluation.

## Changes

- Added a frozen current-digest pass-4 fixture with two reverse-flow skill lineage items and four adjacent general-agent rows.
- Extended the pass-4 handoff dispatcher and builder for `github-growth-20260706T052238.803216Z`.
- Added a regression test for bounded skill-route lanes, controller recomputation, general-agent eval gating, and disabled runtime/external actions.
- Documented the current pass-4 interpretation in `docs/skill-route-discovery.md`.

## Validation

```powershell
$env:PYTHONPATH='src'; pytest tests/test_skill_routing.py -q -k 20260706T052238
$env:PYTHONPATH='src'; pytest tests/test_skill_routing.py -q -k "20260706T052238 or 20260706T050238 or 20260706T040238"
$env:PYTHONPATH='src'; pytest tests/test_docs_contracts.py -q -k skill_route
```

All validation passed. `PYTHONPATH=src` was required because the default interpreter resolves `blackhole_agent` to the sibling checkout at `C:\Users\svmes\Documents\Playground\blackhole-agent\src` instead of this worktree.

## Review Notes

- No external skill activation, provider launch, external harness execution, remote execution, profile write, memory write, raw upstream body export, raw source URL export, or raw replay command export is enabled.
- Self-model was read and left unchanged because the existing preference already covers rollback-backed local evolution with narrow safety review.
