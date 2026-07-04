# Skill Route Discovery Pass 3 Current Digest

Source digest: `github-growth-20260704T142434.764913Z`
Rollback artifact: `artifacts/rollback/20260704T142433Z-skill-route-discovery-pass3-current-digest/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill` presents a public Codex/AI Agent skill package with install and script usage pressure. Local interpretation keeps that pressure diagnostic only.
- `lyra81604/zhengxi-views` presents a public Agent Skill with source-citation and advice-boundary metadata.
- `Qwen-AgentWorld`, `Fundamental-Ava`, and `Awesome-Blender-Seedance-Workflow-Usecases` are treated as adjacent general-agent or workflow projects without direct skill-route inheritance.

## Hypothesis

Current pass-3 route discovery should expose an operator-visible local replay lane for this digest before pass 4. Skill and route evidence should map only to documentation, config, test, or code_patch lanes, while adjacent general-agent/workflow evidence remains in `agent_harness_eval_required` until bounded local harness evaluation exists.

## Change

- Added a current digest fixture for `github-growth-20260704T142434.764913Z`.
- Extended `current_digest_pass3_route_to_validation_lane` to map the current proposal IDs:
  - `p1-skill-route-discovery-fixture`
  - `p2-codex-workflow-gate-documentation`
  - `p4-route-classification-matrix`
  - `p3-agent-harness-eval-smoke-tests`
- Added focused regression coverage and updated `docs/skill-route-discovery.md`.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T142434
python -m pytest tests/test_skill_routing.py -q -k "20260704T142434 or 20260704T130435"
```

Result:

- `1 passed, 269 deselected`
- `3 passed, 267 deselected`

## Review Notes

- No upstream skill code is installed, imported, cloned, or executed.
- Operator packets export hashes and bounded lane names, not raw GitHub URLs, replay command bodies, target paths, provider inputs, or upstream bodies.
- Self-model was reviewed and left unchanged because it already supports rollback-backed local evolution with narrow safety review.
