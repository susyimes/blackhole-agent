# Skill Route Discovery Pass 1 Bounded Fork Cluster

- Source digest: `github-growth-20260703T064052.697831Z`
- Capability slice: `skill-route-discovery`
- Rollback ref: `refs/blackhole/rollback/20260703T064202Z-skill-route-discovery-pass1`
- Rollback artifact: `artifacts/rollback/20260703T064202Z-skill-route-discovery-pass1/rollback-point.json`

## Hypothesis

Reverse-flow-skill fork activity is useful route pressure, but it must not
become install, runtime, provider, external skill, or remote-execution
authority. The local operator surface should convert the fork cluster into one
bounded pass-1 validation lane and keep unrelated general-agent or
workflow-only projects behind agent-harness evaluation.

## Evidence Used

- `https://github.com/chishubiao/reverse-flow-skill`
- `https://github.com/kaijiang666/reverse-flow-skill`
- `https://github.com/lanmomoling/reverse-flow-skill`
- `https://github.com/lingbol088-spec/reverse-flow-skill`
- Carried digest evidence for `https://github.com/lyra81604/zhengxi-views`

The reviewed GitHub pages showed a public reverse-flow-skill repository shape
with AI Agent/Codex skill packaging, `skills/reverse-flow`, local sandbox or
CTF reverse-analysis framing, scripts, and workflow language. No upstream code
was cloned, installed, executed, or activated.

## Change

- Added a 06:40 digest pass-1 fixture:
  `tests/fixtures/skill_route_discovery/current_digest_20260703T064052_pass1_validation_lane.json`.
- Extended `current_digest_pass1_validation_lane` for the new source digest:
  reverse-flow fork-cluster evidence selects local `test`;
  zhengxi-views selects local `documentation`; Qwen-AgentWorld,
  Fundamental-Ava, and Seedance workflow evidence select
  `agent_harness_eval_required`.
- Preserved unsupported lane pressure from pass-1 candidates so install,
  provider-runtime, and runtime-execution wording appears only as downgraded
  lane evidence.
- Documented the current pass in `docs/skill-route-discovery.md`.

## Self-Model Decision

`docs/self-model.md` was left unchanged. Its current preference for
rollback-backed, locally validated behavior changes already matches this run,
and the new evidence did not show that the self-model needs to be rewritten,
renamed, contradicted, or simplified.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260703T064052
python -m pytest tests/test_skill_routing.py -q -k "current_digest_pass1_validation_lane or 20260703T064052"
python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery_doc
python -m pytest tests/test_skill_routing.py -q
```

Result: passed.

## Review Notes

- Runtime action, provider launch, external skill activation, external agent
  activation, external harness execution, and remote execution remain denied.
- The operator lane remains body-free: raw source URLs, raw evidence URLs,
  replay commands, target paths, and upstream bodies are not exported.
- Fork rows are correlated popularity and lineage pressure only; they do not
  multiply implementation authority.
