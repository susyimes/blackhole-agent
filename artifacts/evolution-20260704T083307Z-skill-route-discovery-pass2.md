# Evolution Run: skill-route-discovery pass 2

- Source digest: `github-growth-20260704T083309.688268Z`
- Branch: `codex/blackhole-evolve/20260704T083402.506827-add-or-extend-a-local-skill-route-discovery-vali`
- Rollback artifact: `artifacts/rollback-20260704T083307Z-skill-route-discovery-pass2.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260704T083307Z-skill-route-discovery-pass2`

## Focused Evidence

- `https://github.com/lingbol088-spec/reverse-flow-skill`: interpreted as Codex workflow-gate skill evidence because the public repository exposes a `skills/reverse-flow` skill layout, scripts, local sandbox/CTF framing, and install/runtime pressure that must stay diagnostic.
- `https://github.com/lyra81604/zhengxi-views`: interpreted as generic/source-cited Agent Skill evidence with `SKILL.md`, skill metadata, references, evals, scripts, citation boundaries, and non-advice framing.
- `https://github.com/Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: interpreted as workflow/usecase evidence without a direct skill workflow route hint; it requires local `agent_harness_eval_required` before adoption scope.
- `https://github.com/QwenLM/Qwen-AgentWorld`: interpreted as general-agent benchmark/world-model evidence; it requires local `agent_harness_eval_required` before implementation scope.

## Hypothesis

The active pass-2 slice should expose a current-digest, operator-visible validation lane that maps skill-like evidence into bounded documentation, config, test, or code_patch lanes while keeping general-agent and workflow-usecase evidence behind agent-harness evaluation. This improves replayability for the supervisor without adding runtime, provider, remote, push, promotion, or restart authority.

## Change

- Added the `github-growth-20260704T083309.688268Z` selector to the existing current-digest pass-2 route lane.
- Added a frozen metadata-only fixture for the current digest.
- Added a regression test asserting p1/p2 skill-route lanes, p3 harness-gated adjacent rows, and body-free operator output.
- Documented the current digest interpretation in `docs/skill-route-discovery.md`.

## Validation

Focused validation:

```powershell
python -m pytest tests/test_skill_routing.py -q -k 20260704T083309
```

Result: passed, 1 passed and 255 deselected.

Regression check:

```powershell
python -m pytest tests/test_skill_routing.py -q -k "20260704T083309 or 20260704T071309"
```

Result: passed, 2 passed and 254 deselected.

## Review Notes

- Self-model left unchanged: it already matches this run's preference for rollback-backed, locally validated behavior changes.
- No upstream code is imported or executed.
- Adjacent general-agent and workflow-usecase rows remain `agent_harness_eval_required` with no direct lanes before local harness evaluation.
