# Skill Route Discovery Pass 3: General Agent Review Queue

Source digest: `github-growth-20260624T043356.363880Z`

Rollback point:

- Artifact: `artifacts/rollback/20260624T043511Z-skill-route-discovery-pass3-agent-harness-eval.md`
- Ref: `refs/blackhole/rollback/20260624T043511Z-skill-route-discovery-pass3-agent-harness-eval`
- HEAD: `f42d577d50ffdeb8e8512d0be24a4eb2be634fd4`

Evidence reviewed:

- `https://github.com/omnigent-ai/omnigent`
- `https://github.com/omnigent-ai/omnigent/pull/1084`

Reusable lesson:

Omnigent presents a meta-harness surface where harness-specific behavior must be validated against local evidence before activation. The public PR review for per-turn ACP token usage treated stream accounting details as harness-specific and gated confidence through tests/e2e evidence. The local analogue is to expose general-agent claims as bounded review lanes before allowing `agent_harness_eval_lane` activation.

Change:

- Added `general_agent_route_review_queue` to `agent_harness_eval_lane` output.
- The queue renders mapped and unmapped general-agent claims as body-free local rows.
- Mapped claims choose local `test` validation when a capability exists.
- Unmapped claims choose local `documentation` first and remain blocked.
- Runtime action, external harness execution, provider launch, remote execution, raw source URL export, claim body export, and upstream body export remain denied.
- Updated `docs/skill-route-discovery.md` with the source digest lesson and activation boundary.

Validation:

- `pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane` passed: 3 passed, 142 deselected.
- `pytest tests/test_harness_eval.py -q` passed: 145 passed.

Review notes:

- No offensive behavior or privacy-leakage route was introduced.
- No upstream code was installed, imported, cloned, or executed.
- The self-model was read and left unchanged because this run produced a direct behavior improvement and did not need to revise the current local-evolution preference.
