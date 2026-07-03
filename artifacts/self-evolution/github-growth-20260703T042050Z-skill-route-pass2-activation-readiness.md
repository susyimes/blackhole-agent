# Skill Route Discovery Pass 2 Activation Readiness

Source digest: `github-growth-20260703T042050.326474Z`
Capability slice: `skill-route-discovery`
Branch: `codex/blackhole-evolve/20260703T042153.530988-run-a-bounded-skill-route-discovery-validation-f`
Rollback artifact: `artifacts/self-evolution/github-growth-20260703T042050Z-rollback.md`

## Hypothesis

The current skill-route window should expose an operator-visible pass-2 readiness surface instead of only row-level validation. Reverse-flow-skill should prove `skill_route_discovery_first` before secondary Codex workflow handling, zhengxi-views should stay a candidate-specific skill workflow lane, and Qwen-AgentWorld/Fundamental-Ava should remain in `agent_harness_eval_required` before local follow-up work.

## Evidence Used

- `https://github.com/lingbol088-spec/reverse-flow-skill`: treated as metadata evidence for a Codex workflow gate and skill package layout.
- `https://github.com/lyra81604/zhengxi-views`: treated as metadata evidence for a source-cited skill workflow package.
- `https://github.com/QwenLM/Qwen-AgentWorld` and `https://github.com/TianhangZhuzth/Fundamental-Ava`: treated as general agent projects requiring a local harness-eval lane before implementation.

No upstream code was imported or executed.

## Change

- Added the `github-growth-20260703T042050.326474Z` pass-2 proposal mapping.
- Added optional pass-2 `candidate_name_terms` filtering so concrete repository probes do not absorb adjacent candidates sharing the same route profile.
- Added `skill_route_discovery_current_digest_pass2_activation_readiness`, a body-free readiness surface that lists bounded next operator lanes and keeps external activation denied.
- Added a fixture and regression test for the current digest.

## Validation

Passed:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_routing.py -q -k "20260703T042050 or 20260703T025735"
```

Result: `2 passed, 196 deselected`.

## Review Notes

- The readiness surface is not an activation grant. It records `runtime_action: none` and denies external skill activation, external agent activation, external harness execution, provider runtime launch, and remote execution.
- The self-model was left unchanged because it already describes the run preference for rollback-backed, locally validated behavior changes over standalone validation reports.
