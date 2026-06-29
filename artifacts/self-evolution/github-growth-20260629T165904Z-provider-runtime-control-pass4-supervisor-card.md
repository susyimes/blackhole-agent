# Provider Runtime Control Pass 4 Supervisor Card

Source digest: `github-growth-20260629T165904.193832Z`

Hypothesis: the final provider-runtime-control pass should expose an operator-visible,
body-free provider-runtime replay card from the local-kernel handoff, rather than
leaving provider readiness split across nested completion diagnostics.

Evidence reviewed:

- `https://github.com/dongshuyan/compass-skills`: treated as skill ecosystem and
  state-handoff evidence only.
- `https://github.com/lyra81604/zhengxi-views`: treated as generic skill workflow
  evidence only.
- `https://github.com/QwenLM/Qwen-AgentWorld`: treated as adjacent general-agent
  evaluation evidence, not a skill-route candidate.

Changed behavior:

- Added `local_kernel_handoff.provider_runtime_supervisor_card`.
- The card projects existing `provider_runtime_completion_handoff` and
  `provider_runtime_final_diagnostics` into a compact supervisor replay surface.
- The card exports only statuses, booleans, counts, hashes, and next-action codes.
- Runtime action, external skill activation, external agent activation, external
  harness execution, provider launch, remote execution, raw provider values, raw
  diagnostics, raw replay commands, raw source URLs, target paths, and upstream
  bodies remain denied.

Validation:

- `python -m pytest tests/test_harness_eval.py -q -k "20260629T165904"` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs or 20260629T165904"` passed.
- `python -m pytest tests/test_harness_eval.py -q -k "provider_runtime_control_pass4_surfaces_completion_handoff"` passed.
- `python -m pytest tests/test_docs_contracts.py -q` passed.
- `python -m pytest tests/test_harness_eval.py -q` passed.

Rollback:

- Rollback artifact: `artifacts/rollback/20260629T165903Z-provider-runtime-control-pass4-completion.md`

Review notes:

- The self-model was read and left unchanged; it already states that local
  evolution is allowed only when rollback-backed, validated, and policy-bounded.
- No provider was launched. The provider sample is local metadata for replay only.
