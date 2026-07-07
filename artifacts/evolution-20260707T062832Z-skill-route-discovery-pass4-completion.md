# Skill Route Discovery Pass 4 Completion

Source digest: `github-growth-20260707T062834.999092Z`

Rollback point:
`artifacts/rollback/20260707T062832Z-skill-route-discovery-pass4-completion/rollback-point.md`

## Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow shape with local sandbox, staged reverse-analysis workflow, install/run/script pressure, and skill package layout.
- `https://github.com/Pluviobyte/rnskill`: generic AI Agent skill collection with `SKILL.md`-compatible package and marketplace/config pressure.
- `https://github.com/InternScience/Agents-A1`, `https://github.com/TianhangZhuzth/Fundamental-Ava`, and `https://github.com/shepherd-agents/shepherd`: broad agent projects with runtime, evaluation, replay, or autonomous-agent claims but no local skill-route activation proof.

## Hypothesis

The final pass should produce an operator-visible completion handoff, not another isolated fixture. Skill/workflow repositories should stay bounded to documentation, config, test, or code_patch lanes, while adjacent general-agent projects should be queued into a local harness-eval recovery workflow before any direct implementation or runtime route.

## Change

- Extended `current_pass4_completion_handoff` to recognize `github-growth-20260707T062834.999092Z`.
- Added a `general_agent_recovery_workflow` section to the pass-4 handoff. It records the required local harness fixture fields and blocks direct code/config proposals, runtime action, external harness execution, provider launch, and remote execution before local evaluation.
- Updated the skill-route docs and docs contract for the current digest.
- Left `docs/self-model.md` unchanged because its current preference already matches this run: locally validated behavior paths are preferred over report-only refinement, with permissions still external.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k "20260707T050834 or 20260707T062834"`: passed, 2 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k "current_pass4_completion_handoff or 20260707T062834"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q`: passed, 366 tests.
- `python -m pytest tests/test_docs_contracts.py -q`: passed, 15 tests.

## Review Notes

- No upstream code, prompts, scripts, packages, or runtime behavior were imported or executed.
- External evidence URLs remain evidence only; route packet outputs remain body-free and hash-based.
- Supervisor activation, commit, promotion, push, and restart remain external handoff actions.
