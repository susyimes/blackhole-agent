# Run Notes: upstream-evidence-capability pass 1

- Source digest: `github-growth-20260712T173308.992902Z`
- Branch: `grok/blackhole-evolve/20260712T173345.234156-borrow-cautiously-from-smilelikeye-agent-chief-p`
- Theme: `upstream-evidence-capability` (pass 1 of 4)
- Rollback: `artifacts/rollback/20260712T173647Z-upstream-evidence-capability-pass1.md`
- Rollback ref: `refs/rollback/blackhole-agent/20260712T173647Z-upstream-evidence-capability-pass1`

## Hypothesis

Public agent-ecosystem signals should become one operator-visible local capability step, not another isolated note. Hy3-style untitled pull request evidence should force compare-before-draft; agent-chief privacy release evidence should remain a hard review-only boundary without exporting sensitive data.

## Changes

- Added `upstream_evidence_capability_step` digest/plan packet in `src/blackhole_agent/github_growth.py`.
- Wired the packet into digest construction, proposal synthesis refresh, memory update, markdown digests, self-evolution tasks, and codex/grok manifests.
- Documented the surface in `docs/architecture.md` and `docs/upstream-evidence-interpretation.md`.
- Grounded a self-model habit for this slice in `docs/self-model.md`.
- Added focused unit and docs-contract tests.

## Validation

- `pytest tests/test_github_growth.py -q -k "upstream_evidence_capability_step or self_evolution_plan_carries_upstream"`: 3 passed
- `pytest tests/test_docs_contracts.py -q -k "capability_step or architecture_links_upstream"`: 2 passed
- `pytest tests/test_github_growth.py tests/test_docs_contracts.py -q -k "not test_github_growth_help"`: 138 passed, 1 deselected
- Pre-existing failure left untouched: `test_github_growth_help` (CLI help ANSI output omits `--trend-query` in this environment)

## Self-model

Updated `docs/self-model.md` with an Upstream Evidence Habit grounded in this run's agent-chief/Hy3 evidence.

## Review notes

- Proposal `11604932169-1` remains privacy-leakage review-only; no tokens, credentials, secrets, private chats, or PII are exported by the new packet.
- Hy3 untitled PR proposals select `local_pr_compare_before_draft` with autonomous apply denied until local compare and stronger confirmation exist.
- Runtime action remains `none`; provider launch, external harness execution, remote execution, push/promotion, and kernel restart stay denied.
