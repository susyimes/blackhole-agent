# Evolution Run: skill-route-discovery pass 2 current window

- Branch: `codex/blackhole-evolve/20260703T172019.572391-add-a-local-skill-route-discovery-validation-fix`
- Rollback artifact: `artifacts/rollback-20260703T171921Z-skill-route-discovery-pass2-current-window.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260703T171921Z-skill-route-discovery-pass2-current-window`
- Source digest: `github-growth-20260703T171922.860113Z`
- Self-model: read and left unchanged. The current text already favors rollback-backed, locally validated behavior changes, and this run had stronger evidence for route-controller behavior and validation coverage than for revising self-description text.

## Evidence Interpretation

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted as Codex-oriented skill workflow evidence. It may enter `skill_route_discovery` only as a bounded local validation row and must record `skill_route_discovery_first`.
- `https://github.com/lyra81604/zhengxi-views`: interpreted as generic and source-cited Agent Skill workflow evidence. It may map only to documentation, config, test, or code_patch lanes.
- `https://github.com/Forsy-AI/agent-apprenticeship` and `https://github.com/QwenLM/Qwen-AgentWorld`: interpreted as adjacent general-agent project evidence without explicit skill workflow route authority. They remain behind `agent_harness_eval_required`.

## Hypothesis

Pass 2 should expose an operator-visible validation lane for the current digest using the active proposal names, including the config/documentation lanes requested by the window, while preventing adjacent general-agent projects from inheriting direct implementation or runtime routes.

## Changes

- Registered `github-growth-20260703T171922.860113Z` in the pass-2 skill-route local validation path.
- Added a local harness fixture for reverse-flow-skill, zhengxi-views, and adjacent general-agent evidence.
- Extended the active pass-2 slice review to accept `codex_workflow_gate` as a required skill-route profile for this digest.
- Documented the current pass-2 route split and added a docs contract phrase.

## Validation

- `python -m pytest tests/test_harness_eval.py -q -k 20260703T171922`: passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or 20260703T171922"`: passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_bounded_matrix`: passed.

## Review Notes

- No external repository code was executed.
- Raw source URLs and replay commands are expected to remain out of the structured operator lane.
- Provider launch, external harness execution, remote execution, and external activation remain denied.
