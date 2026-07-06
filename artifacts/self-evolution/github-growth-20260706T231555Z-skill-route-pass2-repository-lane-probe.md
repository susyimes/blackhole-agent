# Skill Route Discovery Pass 2 Repository Lane Probe

- Source digest: `github-growth-20260706T231555.494659Z`
- Capability slice: skill-route-discovery pass 2 of 4
- Rollback ref: `refs/rollback/20260707T000000Z-skill-route-discovery-pass2-local-lanes`
- Evidence reviewed: `https://github.com/lingbol088-spec/reverse-flow-skill`, `https://github.com/shepherd-agents/shepherd`

## Hypothesis

Reverse-flow-style Codex skill repositories expose enough body-free structure
to select bounded local validation lanes before activation: skill package
paths, `SKILL.md`, references, scripts, local sandbox framing, and workflow
language. The local controller should surface that lane choice directly while
keeping install/run/provider/runtime pressure diagnostic.

## Change

Added `build_skill_route_discovery_repository_lane_probe`, an operator-visible
pre-activation probe for repository summaries. It emits source hashes, matched
terms, layout and metadata signals, route profiles, allowed lanes, a selected
local lane, and stripped unsupported pressure. It does not export raw source
URLs or upstream bodies and keeps runtime action, external activation, external
harness execution, provider launch, and remote execution disabled.

Added focused unit coverage for synthetic reverse-flow-like metadata plus
ambiguous Codex/workflow/developer-skill repositories that should remain
ignored.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference already covers
this run: prefer locally validated behavior changes over validation-report-only
work, keep rollback and validation explicit, and treat provider/runtime and
skill-route improvements as valid local evolution targets.

## Validation

Focused validation passed:

```powershell
pytest tests/test_skill_routing.py -q -k repository_lane_probe
```

Broader skill-routing validation also passed:

```powershell
pytest tests/test_skill_routing.py -q
```

Result: `353 passed`.

## Review Notes

The new probe is classification-only. It does not fetch, clone, import,
install, execute, or activate upstream skill code. Ambiguous rows are included
as ignored metadata so future route discovery can distinguish genuine skill
packages from repositories that only mention skill-like terms.
