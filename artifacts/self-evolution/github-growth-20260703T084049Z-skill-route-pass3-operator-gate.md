# Skill Route Discovery Pass 3 Operator Gate

Source digest: `github-growth-20260703T084049.971768Z`

Capability slice: `skill-route-discovery`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`
  - Public repository shape shows an Agent/Codex skill package under `skills/reverse-flow`, a local CTF/crackme/sandbox workflow, scripts, and installation/runtime pressure.
  - Reusable lesson: Codex skill-workflow evidence should be validated through `skill_route_discovery_first` before any secondary workflow or runtime interpretation.
- `https://github.com/lyra81604/zhengxi-views`
  - Public repository shape shows `SKILL.md`, `skill.yml`, `references`, `evals`, `scripts`, source-cited workflow boundaries, and non-investment-advice limits.
  - Reusable lesson: generic Agent Skill evidence can enter bounded local lanes, but it is still evidence for validation rather than installation or activation.

## Hypothesis

Pass 3 should give operators a compact, replayable gate that says whether the current skill-route rows are ready for bounded local validation, while keeping general agent projects behind `agent_harness_eval_required`.

## Change

- Added `current_pass3_operator_validation_gate` to the pass-3 route readiness index.
- The gate confirms Codex workflow rows use `skill_route_discovery_first`.
- The gate keeps the lane envelope limited to documentation, config, test, and code_patch.
- The gate denies runtime action, provider launch, external harness execution, remote execution, raw URL export, and upstream body export.
- Added a focused proposal-eval regression for the current reverse-flow plus zhengxi plus general-agent mix.
- Updated `docs/skill-route-discovery.md` with the expected validation path.

## Self-Model Decision

`docs/self-model.md` was read and left unchanged. The current text already prefers locally validated behavior changes over report-only scaffolding and does not conflict with this run.

## Validation

- `python -m pytest tests/test_proposal_eval.py -q -k current_pass3_operator_gate`: passed, 1 passed.
- `python -m pytest tests/test_proposal_eval.py -q -k "current_pass3_operator_gate or skill_route_discovery"`: passed, 5 passed.
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc`: passed, 2 passed.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260703T044050 or skill_route_discovery_current_digest_20260703T060050"`: no tests selected in this checkout.
- `python -m pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane_pass3_selection or pass3_route_to_validation or pass3_route_evidence_gate"`: passed, 2 passed.

## Review Notes

- No offensive behavior, unauthorized access, or privacy-leakage route was implemented.
- The reverse-flow source has security/reverse-engineering framing; local handling remains metadata-only and does not install, run, copy, or activate upstream code.
- Activation, restart, promotion, push, and rollback execution remain supervisor-owned.
