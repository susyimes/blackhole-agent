# Skill Route Discovery Pass 3 Validation Lane

Source digest: `github-growth-20260703T044050.250851Z`
Capability slice: `skill-route-discovery`
Branch: `codex/blackhole-evolve/20260703T044146.257387-run-a-bounded-skill-route-discovery-validation-l`
Rollback artifact: `artifacts/self-evolution/github-growth-20260703T044050Z-rollback.md`
Rollback ref: `refs/rollback/blackhole-agent/20260703T044050Z-skill-route-discovery-pass3`

## Hypothesis

The active pass-3 skill-route window should expose an operator-visible
`current_digest_pass3_route_to_validation_lane` for the current digest rather
than falling back to older generic pass-3 proposal IDs. zhengxi-views should be
validated as a source-cited skill workflow route, reverse-flow-skill should keep
`skill_route_discovery_first` before any Codex workflow gate code patch, and
Qwen-AgentWorld/Fundamental-Ava should remain adjacent agent-harness evaluation
rows.

## Evidence Used

- `https://github.com/lyra81604/zhengxi-views`: observed as a public Agent Skill
  repository with `SKILL.md`, `skill.yml`, references, evals, scripts,
  source-cited workflow language, and an explicit non-investment-advice
  boundary.
- `https://github.com/lingbol088-spec/reverse-flow-skill`: observed as a Codex
  and AI Agent skill package with `skills/reverse-flow/SKILL.md`, scripts,
  local sandbox/CTF/crackme context, and workflow gate language.
- `https://github.com/QwenLM/Qwen-AgentWorld`: observed as a general agent world
  model and benchmark project, not a skill-route package.

No upstream code was imported or executed.

## Change

- Added a frozen `github-growth-20260703T044050.250851Z` pass-3 fixture.
- Extended `current_digest_pass3_route_to_validation_lane` with current digest
  proposal IDs and candidate-name filters so reverse-flow and zhengxi rows do
  not absorb each other's route profiles.
- Added a regression test proving the pass-3 surface is ready, body-free, and
  keeps adjacent general-agent projects in `agent_harness_eval_required`.
- Documented the new pass-3 handoff in `docs/skill-route-discovery.md`.

## Validation

Passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "20260703T044050 or 20260703T042050"
```

Result: `2 passed, 197 deselected`.

Passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc
```

Result: `2 passed, 9 deselected`.

## Self-Model

`docs/self-model.md` was read and left unchanged. It already supports
rollback-backed, locally validated behavior changes and the narrow safety
boundary used by this pass; this run had stronger evidence for a route-surface
change than for revising self-description text.

## Review Notes

- The reverse-flow row has proposal kind `code_patch` but selects the local
  `test` lane first. The queued code_patch lane remains bounded until the
  focused validation proves `skill_route_discovery_first`.
- The pass-3 surface exports selected item IDs, route profiles, lane names,
  source hashes, and replay command hashes. It does not export raw source URLs,
  replay command bodies, target paths, provider inputs, upstream bodies, or
  activation authority.
- Runtime action, external skill activation, external agent activation,
  external harness execution, provider runtime launch, and remote execution
  remain denied.
