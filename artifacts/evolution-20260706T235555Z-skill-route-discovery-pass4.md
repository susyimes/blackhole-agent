# Evolution Run: skill-route-discovery pass 4 completion

- Source digest: `github-growth-20260706T235555.501156Z`
- Rollback ref: `refs/blackhole-rollback/20260706T235555-skill-route-discovery-pass4`
- Rollback artifact: `artifacts/rollback/20260706T235555-skill-route-discovery-pass4.md`
- Self-model: read and left unchanged; it already matched the run's local-validation-first policy and did not add behavior.

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow package with `skills/reverse-flow`, `SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, plus install/run pressure that must remain diagnostic.
- `https://github.com/InternScience/Agents-A1`: general agent/evaluation trend evidence without local skill workflow route evidence.
- `https://github.com/shepherd-agents/shepherd`: general agent runtime/replay substrate trend evidence without local skill workflow route evidence.
- Proposal context also carried Qwen-AgentWorld and Fundamental-Ava as adjacent general-agent examples for the local fixture.

## Hypothesis

The final pass should expose an operator-visible `current_digest_pass4_completion_handoff` for the current proposal IDs. Skill workflow evidence should enter `skill_route_discovery` first and map only to documentation, config, test, or code_patch lanes. General-agent project evidence should remain behind `agent_harness_eval_required`, with no direct runtime or code patch lane before local harness validation.

## Changes

- Added the `github-growth-20260706T235555.501156Z` digest to the existing pass-4 completion dispatcher and shared handoff builder.
- Added a current digest fixture for the reverse-flow plus general-agent trend window.
- Added a focused regression asserting bounded skill-route lanes, agent-harness gating, body-free output, and denied runtime/provider/external execution.
- Documented the current source digest interpretation in `docs/skill-route-discovery.md`.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T235555`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260706T235555 or 20260706T223555"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 3 tests.

## Review Notes

- No upstream skill code was installed, cloned, imported, or executed.
- Runtime action, external skill activation, external agent activation, external harness execution, provider launch, remote execution, raw URL export, raw command export, and upstream body export remain denied by the tested handoff.
