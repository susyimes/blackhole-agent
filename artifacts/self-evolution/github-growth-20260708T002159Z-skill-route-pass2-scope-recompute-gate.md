# Skill Route Discovery Pass 2: Scope Recompute Gate

- Source digest: `github-growth-20260708T002159.945917Z`
- Branch: `codex/blackhole-evolve/20260708T002248.564641-run-a-bounded-skill-route-discovery-lane-for-rev`
- Rollback point: `artifacts/rollback/20260708T002248Z-skill-route-discovery-pass2-active-window/rollback-point.md`
- Self-model: unchanged

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public repository presents a Codex/AI Agent reverse-flow skill with trigger phrase, local sandbox/CTF assumptions, staged workflow, and diagnostic script examples.
- `https://github.com/Pluviobyte/rnskill`: public repository presents a generic `SKILL.md` collection with skills, docs, tools, marketplace metadata, and install examples.
- `https://github.com/shepherd-agents/shepherd`: public repository presents a reversible agent execution runtime substrate, which is adjacent general-agent evidence rather than a skill-route lane.
- `https://github.com/Tencent-Hunyuan/Hy3/issues/1`: public issue requests runnable provider quickstart/examples; this remained background provider-preflight pressure and was not selected for the current pass-2 route gate.

## Hypothesis

The active pass-2 window needs an operator-visible gate that confirms reverse-flow and rnskill evidence become bounded local validation lanes only after controller recomputation, while Shepherd-style general-agent evidence remains behind agent harness evaluation.

## Change

Added `skill_route_discovery_current_pass2_scope_recompute_gate` to the proposal lane map. The gate:

- maps reverse-flow to a `test` lane with `codex_workflow_gate` evidence;
- maps rnskill to a `documentation` lane as generic skill workflow evidence;
- records `controller_recomputed_scope: local_validation_candidate`;
- records `focused-evidence-review`;
- requires controller recomputation before any code-patch lane proceeds;
- keeps adjacent general-agent evidence at `agent_harness_eval_required` and `runtime_action: none`.

Added a focused fixture and test for source digest `github-growth-20260708T002159.945917Z`, plus a docs note with the replay command.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k current_pass2_scope_recompute_gate`
  - Result: `1 passed, 401 deselected`
- `python -m pytest tests/test_skill_routing.py -q`
  - Result: `402 passed`
- `python -m pytest tests/test_docs_contracts.py -q`
  - Result: `25 passed`

## Review Notes

- No external skill activation, install, provider launch, harness execution, remote execution, restart, promotion, profile write, or memory write was performed.
- The self-model was left unchanged because its current preference already supports rollback-backed, locally validated behavior changes and this run had a concrete routing behavior path.
- The rnskill row uses a gate-local generic fallback when the candidate name matches `rnskill`; this avoids changing global classifier behavior while preserving the current proposal's generic skill collection intent.
