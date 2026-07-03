# Evolution Run: skill-route-discovery pass 2

- Source digest: `github-growth-20260703T195925.017787Z`
- Branch: `codex/blackhole-evolve/20260703T200027.572540-create-or-run-a-bounded-local-validation-probe-f`
- Rollback ref: `refs/blackhole-rollback/20260703T195925-skill-route-discovery-pass2`
- Rollback artifact: `artifacts/rollback-20260703T195925Z-skill-route-discovery-pass2.md`
- Self-model: read and left unchanged; the existing preference for rollback-backed local evolution already matched this run.

## Evidence

Reviewed bounded proposal URLs only:

- `https://github.com/TaoDevil/reverse-flow-skill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/Forsy-AI/agent-apprenticeship`

The reusable lesson is that public skill/workflow repository evidence should
enter a local validation lane before activation. Reverse-flow-style Codex skill
workflow evidence is kept in `skill_route_discovery_first`; source-cited
skill-workflow evidence stays documentation-first; general agent projects stay
behind `agent_harness_eval_required`.

## Change

- Added current digest handling for `github-growth-20260703T195925.017787Z` in
  `current_digest_pass2_local_validation_lane`.
- Added frozen direct and local-harness fixtures for the current pass.
- Added focused assertions that reverse-flow-skill rows expose downgraded
  install/runtime pressure while keeping runtime action, provider launch,
  external activation, and external harness execution denied.
- Documented the current pass in `docs/skill-route-discovery.md`.

## Validation

Passed:

```powershell
python -m pytest tests/test_skill_routing.py tests/test_harness_eval.py -q -k 20260703T195925
python -m pytest tests/test_harness_eval.py -q -k local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery
git diff --check
```

`git diff --check` reported only CRLF normalization warnings for existing file
settings, not whitespace errors.

## Review Notes

- No runtime action, external skill activation, external agent activation,
  provider runtime launch, remote execution, or external harness execution was
  enabled.
- Raw upstream bodies, raw source URLs, raw replay commands, target paths, and
  evidence URLs remain omitted from the lane outputs.
- Promotion, push, restart, and replay remain supervisor-owned.
