# Skill Route Discovery Pass 3 Bounded Lanes

Source digest: `github-growth-20260707T005555.490893Z`

Rollback point:
`artifacts/rollback/20260707T005554Z-skill-route-discovery-pass3-bounded-lanes/rollback-point.md`

## Evidence Reviewed

- `lingbol088-spec/reverse-flow-skill`: public repository page shows a Codex/AI Agent skill workflow package under `skills/reverse-flow`, `SKILL.md`, scripts, references, local sandbox/CTF/crackme framing, install examples, and run examples.
- `InternScience/Agents-A1`: treated as general-agent project evidence without an explicit local skill route signal in this pass.
- `shepherd-agents/shepherd` issue 23: retained as general-agent/provider-harness pressure already covered by local preflight lanes; no provider launch or external harness execution was attempted.
- `Evolink-AI/Awesome-Blender-Seedance-Workflow-Usecases`: treated as workflow/usecase catalog evidence, not an executable skill route.

## Hypothesis

The active pass-3 window should expose an operator-visible replay packet that:

- routes reverse-flow through `skill_route_discovery` first;
- keeps general-agent projects behind `agent_harness_eval_required`;
- gives workflow/usecase collections a distinct evaluation proposal instead of merging them into skill-route evidence;
- exports only body-free routing metadata and command hashes.

## Local Changes

- Extended `current_digest_pass3_replay_packet` for `github-growth-20260707T005555.490893Z`.
- Added a frozen fixture for the current pass-3 evidence window.
- Added a regression test asserting bounded lanes, workflow-usecase separation, and raw URL/command suppression.
- Updated `docs/skill-route-discovery.md` with the current operator replay rule.

## Review Notes

- No upstream code was installed, cloned, or executed.
- Runtime action, provider launch, external harness execution, external skill activation, external agent activation, and remote execution remain disabled.
- The self-model was read and left unchanged because the run produced a concrete routing behavior change and the existing self-model already matches that preference.

## Validation

- `pytest tests/test_skill_routing.py -q -k 20260707T005555` passed.
- `pytest tests/test_skill_routing.py -q` passed.
- `pytest tests/test_docs_contracts.py -q -k skill_route_discovery` passed.
