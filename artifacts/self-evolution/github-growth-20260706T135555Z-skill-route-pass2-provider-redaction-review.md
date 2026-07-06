# Self-Evolution Run: skill-route-discovery pass 2

- Source digest: github-growth-20260706T135555.942816Z
- Capability slice: skill-route-discovery
- Pass: 2 of 4
- Branch: codex/blackhole-evolve/20260706T135654.245095-add-or-extend-local-provider-config-preflight-co
- Rollback ref: refs/rollback/20260706T135554Z-skill-route-discovery-pass2
- Rollback artifact: artifacts/rollback/20260706T135554Z-skill-route-discovery-pass2/rollback-point.md

## Evidence Reviewed

- `lingbol088-spec/reverse-flow-skill` exposes a public Codex-oriented skill package shape with `skills/reverse-flow`, `SKILL.md`, references, scripts, install examples, and run examples.
- `shepherd-agents/shepherd` issue 23 reports a provider CLI lane failure where preflight appears green but execution returns an empty envelope; the diagnostic is useful only behind privacy redaction.
- `InternScience/Agents-A1` is a general agent project with model, evaluation, benchmark, and tool-use claims, not a local skill route.

## Hypothesis

Pass 2 should make the provider preflight failure visible to operators without implementing provider behavior. The reusable local lesson is a bounded review packet: skill evidence maps to documentation/config/test/code_patch lanes, general agent projects wait for agent-harness evaluation, and provider empty-envelope diagnostics remain review-only with explicit redaction assertions.

## Change

- Added current digest pass-2 routing for `github-growth-20260706T135555.942816Z`.
- Added a body-free `provider_config_preflight_redaction_review` packet to the pass-2 lane.
- Extended provider preflight review rows with assertions that command bodies, tokens, private payloads, provider values, source URLs, and upstream bodies are not exported.
- Added a current-digest replay fixture and regression test.
- Updated `docs/skill-route-discovery.md` with the replay path and review-only provider boundary.

## Validation

Focused validation:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src'); python -m pytest tests/test_skill_routing.py -q -k 20260706T135555
```

Result: passed.

## Review Notes

- `p1-provider-cli-preflight-redaction` remains review-only under `privacy-leakage-human-review`.
- No provider runtime, external harness execution, external skill activation, remote execution, profile write, memory write, raw source URL export, raw command body export, raw token export, raw private payload export, raw provider value export, or upstream body export is enabled.
- The self-model was read and left unchanged because the implemented route matches its current rollback-backed local evolution preference while respecting the privacy boundary.
