# Skill Route Discovery Pass 1 Focused Review

- Source digest: `github-growth-20260707T052834.687686Z`
- Branch: `codex/blackhole-evolve/20260707T052928.535030-add-or-run-a-bounded-local-skill-route-discovery`
- Rollback ref: `refs/rollback/20260707T052832Z-skill-route-discovery-pass1-current-digest`
- Rollback artifact: `artifacts/rollback/20260707T052832Z-skill-route-discovery-pass1-current-digest/rollback-point.md`

## Evidence

- `lingbol088-spec/reverse-flow-skill`: treated as Codex workflow-gate skill-route evidence because the public repository exposes a `skills/reverse-flow` package, `SKILL.md`, references, scripts, local sandbox and CTF/crackme framing, install examples, run examples, and staged workflow language.
- `Pluviobyte/rnskill`: treated as generic skill workflow evidence because it is an AI Agent Skills collection for Codex, Claude Code, and `SKILL.md`-oriented workflows, with `skills`, docs, tools, and plugin metadata.
- `InternScience/Agents-A1`, `TianhangZhuzth/Fundamental-Ava`, and `shepherd-agents/shepherd`: treated as adjacent general-agent or runtime/evaluation evidence. They require `agent_harness_eval_required` before any documentation, test, or code_patch follow-up can be selected.

## Hypothesis

The current pass should expose an operator-visible pass-1 review lane for the exact digest instead of leaving the new reverse-flow/rnskill/general-agent split implicit in generic route rows. The lane should preserve local validation requirements, limit skill workflow outputs to documentation, config, test, or code_patch, and keep general-agent projects behind agent-harness evaluation.

## Changes

- Added `current_pass1_focused_review_lane` to `skill_route_discovery_validation_route_packet` for `github-growth-20260707T052834.687686Z`.
- Added a frozen current-digest fixture with reverse-flow, rnskill, Agents-A1, Fundamental-Ava, and shepherd evidence.
- Added regression coverage for bounded skill-route lanes, agent-harness gating, route policy metadata, consistency checks, command hashing, and raw URL/body denial.
- Documented the new pass-1 focused review lane in `docs/skill-route-discovery.md`.

## Self-Model

`docs/self-model.md` was read and left unchanged. Its current preference already matches this run: a reversible local behavior improvement is preferred over a validation-report-only outcome, while upstream install, runtime, provider, external harness, and remote execution remain outside this bounded lane.

## Validation

- `python -m pytest tests/test_skill_routing.py -q -k 20260707T052834`: passed, 1 test.
- `python -m pytest tests/test_docs_contracts.py -q -k 20260707T052834`: passed, 1 test.
- `python -m pytest tests/test_skill_routing.py -q -k "20260707T052834 or 20260707T050834 or 20260707T044834"`: passed, 3 tests.
- `python -m pytest tests/test_docs_contracts.py -q -k "20260707T052834 or skill_route_discovery_doc_records_route_discovery_catalog"`: passed, 2 tests.
- `python -m pytest tests/test_skill_routing.py -q -k validation_route_packet`: passed, 1 test.

## Review Notes

- No upstream skill code was installed, cloned, run, or activated.
- Raw upstream URLs remain fixture input only; packet output exports source hashes and metadata, not raw URLs or upstream bodies.
- Activation, promotion, push, restart, provider launch, external harness execution, and remote execution were not performed.
