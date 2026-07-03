# Skill Route Discovery Pass 1 Current Validation Lane

Source digest: github-growth-20260703T023735.914741Z
Capability theme: skill-route-discovery
Capability pass: 1 of 4
Rollback ref: refs/blackhole-rollback/github-growth-20260703T023735Z
Rollback artifact: artifacts/self-evolution/github-growth-20260703T023735Z-rollback.md

## Evidence Reviewed

- https://github.com/lingbol088-spec/reverse-flow-skill: public Codex / AI Agent skill package with a `skills/reverse-flow` layout, local sandbox/CTF framing, references, scripts, and workflow language.
- https://github.com/lyra81604/zhengxi-views: public Agent Skill evidence with `SKILL.md`, manifest-like metadata, source-cited workflow framing, and advice-boundary signals.
- https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases: workflow/usecase and agent-guided media evidence without a direct skill-route package signal.
- https://github.com/QwenLM/Qwen-AgentWorld: general-agent benchmark/world-model evidence without a direct skill workflow route hint.

## Hypothesis

The current digest should have a replayable pass-1 lane instead of borrowing confidence from the previous reverse-flow pass. Skill/Codex/workflow repository evidence should map only to documentation, config, test, or code_patch with `local_validation_required=true`. Workflow-only and general-agent repository evidence should remain adjacent `agent_harness_eval_required` input before documentation, test, or code_patch follow-up is selected.

## Changes

- Added a `github-growth-20260703T023735.914741Z` branch to the current digest pass-1 skill-route builder.
- Added a frozen body-free fixture for the current digest evidence.
- Added a regression test for bounded skill-route rows, adjacent agent-harness rows, and no runtime/provider/external activation.
- Documented the current digest route interpretation.

## Validation

- `PYTHONPATH=src pytest tests/test_skill_routing.py -q -k "20260703T023735 or 20260703T004121 or 20260703T021735"`: passed, 3 tests.
- `PYTHONPATH=src pytest tests/test_skill_routing.py -q`: passed, 193 tests.
- `PYTHONPATH=src pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260703 or skill_route_discovery_lane"`: passed, 10 tests.
- `PYTHONPATH=src pytest tests/test_docs_contracts.py -q`: passed, 11 tests.

## Review Notes

- The self-model was read and left unchanged. Its current preference for rollback-backed, locally validated evolution matches this run and did not need behavior-shaping edits.
- No external skill was installed, cloned, enabled, or executed. No provider runtime, external harness, remote execution, profile write, or memory write path was activated.
- The quick manual Python probe initially imported a sibling checkout; validation commands were run with `PYTHONPATH=src` to force this worktree.
