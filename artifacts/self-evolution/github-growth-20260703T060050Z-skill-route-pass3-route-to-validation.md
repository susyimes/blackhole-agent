# Skill Route Discovery Pass 3 Route-To-Validation

- Source digest: `github-growth-20260703T060050.289743Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole-agent/rollback/20260703T060050Z-skill-route-discovery-pass3`
- Rollback artifact: `artifacts/self-evolution/github-growth-20260703T060050Z-rollback.md`

## Hypothesis

Reverse-flow-skill style Codex workflow evidence and generic skill repository
evidence should enter one operator-visible pass-3 route-to-validation lane
before activation. The lane should expose only documentation, config, test, or
code_patch follow-up, carry verification uncertainty, and keep general-agent or
workflow-only projects behind local agent-harness evaluation.

## Evidence Used

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/lingbol088-spec/reverse-flow-skill/issues/2`
- `https://github.com/lyra81604/zhengxi-views`
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`
- `https://github.com/QwenLM/Qwen-AgentWorld`

No upstream code was installed, cloned, executed, or activated.

## Change

- Added current-digest fixture
  `tests/fixtures/skill_route_discovery/current_digest_20260703T060050_pass3_route_to_validation.json`.
- Extended `current_digest_pass3_route_to_validation_lane` for the 06:00 digest:
  reverse-flow Codex workflow evidence selects local `test`; generic skill
  workflow evidence selects local `documentation`; adjacent general-agent
  evidence selects `agent_harness_eval_required`.
- Added row-level `verification_uncertainty_reasons` and
  `implementation_route_requires_focused_validation` to the pass-3
  route-to-validation surface.
- Documented the new operator-visible lane in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference for
rollback-backed, locally validated behavior changes is consistent with this
run, and no new evidence showed that the file should be rewritten or renamed.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T060050
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass3_route_to_validation or 20260703T060050"
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc
python -m pytest tests/test_skill_routing.py -q
```

Result: passed.

## Review Notes

- The lane remains body-free: raw source URLs, raw evidence URLs, replay
  commands, target paths, and upstream bodies are not exported.
- Runtime action, provider launch, external skill activation, external agent
  activation, external harness execution, and remote execution remain denied.
- General-agent projects still require local harness evaluation before any
  documentation, test, or code_patch follow-up can be selected.
