# Skill Route Discovery Pass 3 Activation Review

- Source digest: github-growth-20260702T024715.215946Z
- Rollback artifact: artifacts/rollback-20260702T024821Z-skill-route-discovery-pass3.md
- Local rollback ref: refs/blackhole-rollback/20260702T024821-skill-route-discovery-pass3

## Evidence Interpretation

- zhengxi-views exposes explicit Agent Skill shape: `SKILL.md`, `skill.yml`,
  `references/`, `scripts/`, `evals/`, source-citation behavior, and
  non-investment-advice boundaries.
- NVIDIA BioNeMo Agent Toolkit exposes toolkit-style skill catalog shape:
  skill directories, workflow directories, plugin marketplace metadata, and
  `skills.sh.json`.
- Qwen-AgentWorld is general-agent benchmark/evaluation evidence, not a skill
  route signal. It remains behind local `agent_harness_eval_required` before
  any documentation, test, or code patch follow-up.

## Local Change

Pass-3 activation review can now bind a proposal row to specific skill-route
candidate names. This prevents a multi-candidate window from collapsing
BioNeMo toolkit evidence and zhengxi source-cited skill evidence into one
ambiguous row merely because both carry `generic_skill_workflow`.

The new digest fixture proves:

- zhengxi routes to a bounded local test lane with `source_cited_domain_research`.
- BioNeMo routes to a separate bounded local test lane as toolkit-style skill
  catalog evidence.
- Qwen-AgentWorld and Fundamental-Ava stay adjacent and require local harness
  evaluation before implementation routes.
- Runtime execution, provider launch, external harness execution, and raw URL
  export remain denied.

## Validation

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260702T024715 or 20260702T022714 or 20260701T231748"
python -m pytest tests/test_skill_routing.py -q
python -m pytest tests/test_harness_eval.py -q -k "233748_pass4_operator_replay_summary"
```

Results:

- Focused skill-routing regression: 3 passed.
- Full skill-routing suite: 152 passed.
- Related harness replay: 1 passed.

One attempted harness command selected no tests:

```powershell
python -m pytest tests/test_harness_eval.py -q -k "20260701T231748 or current_digest_20260701T231748"
```

It produced 214 deselected tests and no executed tests, so it was replaced by
the actual test-name pattern above.

## Self-Model

`docs/self-model.md` was left unchanged. Its current preference for
rollback-backed, locally validated behavior changes matched this pass and did
not need new structure.
