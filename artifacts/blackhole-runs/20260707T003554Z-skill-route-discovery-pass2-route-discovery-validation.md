# Blackhole Run: skill-route-discovery pass 2 route-discovery validation

Source digest: `github-growth-20260707T003555.486083Z`
Branch: `codex/blackhole-evolve/20260707T003649.764859-run-a-bounded-local-skill-route-discovery-valida`
Rollback artifact: `artifacts/rollback/20260707T003554Z-skill-route-discovery-pass2-route-discovery-validation/rollback-point.md`
Rollback ref: `refs/blackhole-rollback/20260707T003554Z-skill-route-discovery-pass2-route-discovery-validation`

## Evidence Reviewed

- `https://github.com/lingbol088-spec/reverse-flow-skill`: public Codex/AI Agent skill workflow repository with `skills/reverse-flow`, local sandbox/CTF framing, scripts, install examples, and staged reverse-analysis workflow language.
- `https://github.com/InternScience/Agents-A1`: public general agent project signal, useful as harness-evaluation pressure rather than a direct skill-workflow route.
- `https://github.com/shepherd-agents/shepherd/issues/23`: provider/runtime failure evidence for keeping runtime/controller adoption behind local validation.

## Hypothesis

Pass-2 skill-route discovery already separates skill workflow rows from adjacent general-agent rows, but the active slice benefits from a supervisor-visible activation checkpoint that orders controller recomputation, bounded skill-route replay, and adjacent agent-harness replay before any activation candidate is considered.

## Changes

- Added `operator_activation_checkpoint` under `pass2_route_probe`.
- The checkpoint is body-free and non-executable, requires controller recomputation, preserves `skill_route_discovery_first` for skill workflows, keeps general-agent rows in `agent_harness_eval_required`, and denies external skill, agent, harness, provider, remote, and runtime actions.
- Added a current-digest regression for the 2026-07-07 reverse-flow plus general-agent route shape.
- Documented the checkpoint in `docs/architecture.md` and `docs/skill-route-discovery.md`.
- Left `docs/self-model.md` unchanged; the current preference already supports validated behavior changes over report-only artifacts.

## Validation

- `pytest tests/test_harness_eval.py -q -k "20260707_pass2_checkpoint or 20260706T215555_pass2_route_probe"`: passed, 2 tests.
- `pytest tests/test_docs_contracts.py -q -k "skill_route or architecture"`: passed, 4 tests.
- `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_lane or agent_harness_eval_lane"`: passed, 18 tests.
- `pytest tests/test_proposal_eval.py -q -k "route_hint_lane_map or pass2_route"`: passed, 4 tests.

## Review Notes

- No upstream code was cloned, installed, or executed.
- Raw upstream URLs and bodies remain out of the new checkpoint output.
- Activation remains a supervisor/controller decision after local replay; this patch does not restart, promote, push, or run providers.
