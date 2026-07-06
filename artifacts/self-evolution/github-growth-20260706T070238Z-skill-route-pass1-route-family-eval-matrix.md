# Self-Evolution: skill-route-discovery pass 1 route-family eval matrix

- Source digest: `github-growth-20260706T070238.993623Z`
- Created at: 2026-07-06T07:03:53Z
- Branch: `codex/blackhole-evolve/20260706T070322.489737-create-or-extend-a-local-agent-harness-evaluatio`
- Rollback ref: `refs/rollback/20260706T070353Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260706T070353Z-skill-route-discovery-pass1/rollback-point.md`

## Evidence

The current capability window mixed one skill/workflow repository with four adjacent general-agent project signals:

- `lingbol088-spec/reverse-flow-skill`: Codex/AI Agent skill workflow shape with local sandbox and CTF/reverse-analysis framing.
- `InternScience/Agents-A1`: long-horizon/tool-use/evaluation general-agent model signal.
- `QwenLM/Qwen-AgentWorld`: general-agent world-model/evaluation signal.
- `TianhangZhuzth/Fundamental-Ava`: autonomous/collaborative general-agent signal.
- `shepherd-agents/shepherd`: reversible agent runtime substrate signal.

## Hypothesis

Future skill-route discovery passes need an operator-visible mixed-route matrix before activation. A reverse-flow-style skill should remain in bounded local `documentation`, `config`, `test`, or `code_patch` lanes, while general-agent project rows should require `agent_harness_eval_required` and receive no direct implementation lane until local harness evaluation passes.

## Change

- Added `skill_route_discovery_route_family_eval_matrix` to `skill_route_discovery_lane` output.
- Added a current-window local harness fixture covering reverse-flow plus Agents-A1, Qwen-AgentWorld, Fundamental-Ava, and Shepherd.
- Updated aggregate harness assertions and architecture documentation.
- Left `docs/self-model.md` unchanged because the existing preference already supports rollback-backed local experiments and narrow safety review boundaries.

## Validation

Command:

```powershell
python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs or skill_route_discovery_lane or agent_harness_eval_lane"
```

Result: `15 passed, 227 deselected`.

## Review Notes

- No external repositories were cloned, installed, imported, or executed.
- Raw upstream URLs are used only inside local fixture inputs; the new output surface exports hashes/counts/gates and explicit `raw_*_exported: false` flags.
- Runtime action, external skill activation, external agent activation, external harness execution, provider launch, and remote execution remain denied.
