# Skill Route Discovery Pass 2

Source digest: `github-growth-20260706T020239.308113Z`

Rollback point:
`refs/rollback/20260706T020237Z-skill-route-discovery-pass2`

## Hypothesis

The current window should convert reverse-flow-skill repository evidence into a
bounded local skill-route lane while keeping Qwen-AgentWorld, Agents-A1, and the
Seedance workflow-usecase evidence in `agent_harness_eval_required` until local
harness validation exists.

## Change

- Added a frozen current-digest fixture for the pass-2 route split.
- Extended the current digest pass-2 lane classifier to recognize
  `github-growth-20260706T020239.308113Z` and emit the current proposal IDs.
- Documented the route split in `docs/skill-route-discovery.md`.
- Added a regression proving that the emitted lane records repository identity,
  discovered skill workflow signals, bounded local lane mapping, uncertainty
  boundaries, and denied runtime/provider/external execution paths.

## Evidence And Boundaries

Primary evidence URLs carried by the run:

- `https://github.com/lingbol088-spec/reverse-flow-skill`
- `https://github.com/QwenLM/Qwen-AgentWorld`
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`
- `https://github.com/InternScience/Agents-A1`

The implementation records only body-free route metadata in the fixture and
classifier output. It does not import, clone, install, run, activate, launch a
provider, execute an external harness, perform remote execution, write profiles,
write memory, or expose upstream bodies.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260706T020239`
- `python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc_records_bounded_matrix`
- `python -m pytest tests/test_skill_routing.py -q -k "20260705T153637 or 20260706T020239"`

All validations passed.

## Review Notes

The self-model was left unchanged. It already states the current preference for
rollback-backed, locally validated behavior changes and a narrow safety
boundary, and this run did not produce evidence that the file is shaping
behavior beyond that existing description.
