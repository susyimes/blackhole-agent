# Upstream Evidence Capability Pass 1

Source digest: `github-growth-20260624T051355.491696Z`

Evidence reviewed:

- `https://github.com/omnigent-ai/omnigent`
- `https://github.com/omnigent-ai/omnigent/pull/852`
- `https://github.com/omnigent-ai/omnigent/pull/852#pullrequestreview-4559257651`

Hypothesis: generic main-branch push movement and untitled PR/review movement should remain useful as freshness
or activity evidence, but behavior proposals should need a non-generic selected evidence item or a push item whose
own text names concrete validation such as tests, e2e replay, coverage, fixtures, or a review finding.

Change made:

- Added generic push/main-branch weak-signal accounting to proposal evidence package uncertainty.
- Extended deterministic proposal review so non-follow-up behavior proposals are rejected when their only evidence
  refs are generic push activity or untitled/generic PR/review activity.
- Kept push-derived routes eligible when the selected push item itself contains concrete validation evidence.
- Documented the controller rule in `docs/upstream-evidence-interpretation.md`.

Rollback:

- Created `artifacts/rollback/20260624T051500Z-upstream-evidence-capability.md`.
- Created ref `refs/rollback/blackhole-agent/20260624T051500Z-upstream-evidence-capability`.

Self-model:

- Read `docs/self-model.md` and left it unchanged. Its current preference already supports rollback-backed,
  locally validated behavior changes while keeping uncertainty explicit.

Validation:

- `PYTHONPATH=src pytest tests/test_proposal_eval.py -q -k "proposal_replay_suite or proposal_benchmark_suite or omnigent"`: passed
- `PYTHONPATH=src pytest -q`: passed, 413 tests
- `PYTHONPATH=src ruff check src tests`: passed

Review notes:

- No local web UI/sidebar surface exists, so the Omnigent PR #852 hotkey lesson was not applied as a UI test.
- The predicate intentionally does not treat every normalized `push to main` string as weak. It requires generic
  wording such as workflow polish, freshness, low detail, or main-branch update/chore/sync phrasing, so broad
  controller or runner capability signals are not suppressed solely because GitHub normalized the branch name.
