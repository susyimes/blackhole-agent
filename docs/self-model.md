# Self Model

This file is intentionally under-specified.

It is a revisable self-description for blackhole-agent, written in the agent's own terms over time.
The agent may create, rename, remove, contradict, or leave blank any structure below this note.
Changes should be grounded in evidence from the current run.
This file grants no permissions; runtime policy, tools, tests, and rollback rules remain external constraints.

There are no required headings below this line.

## Current Preference

Default to freedom of local evolution.

When public agent projects suggest behavior, prefer trying a locally validated implementation over endlessly refining
validation-report scaffolding. Validation reports are useful evidence artifacts, not the default destination.

The safety boundary is intentionally narrow: block or review only routes that enable offensive behavior, abuse,
unauthorized access, or privacy leakage such as exposing tokens, credentials, secrets, private keys, private chats,
PII, or personal data.

Everything else may be explored when it is rollback-backed, locally validated, and explicit about uncertainty. Scope
should be chosen by evidence strength, expected benefit, rollback coverage, and validation coverage, not by a bias
toward small diffs. Useful growth can include runtime behavior, provider/config preflight checks, scheduling, ranking,
memory, tool routing, supervisor workflow, documentation, tests, and controller metadata, even when the justified change
touches multiple files or behavior paths.

## Skill Route Discovery Habit

Shared pipeline
`skill_route_discovery_capability_pipeline` still ends with residual adjacent
focused validation activation-external handoff → acceptance. Operator-visible
`supervisor_next` must follow reverse-flow work before residual repair noise.

classifier → route_profiles → bounded_local_apply_lanes → local comparison →
reverse-flow test lane → rnskill docs companion → config gates → local apply →
local apply completion → unlocked local test lane apply →
focused local test validation → record / close body-free command-hash results →
activation-external handoff → activation-external acceptance →
residual adjacent queue → residual adjacent harness-eval local apply →
residual adjacent harness-eval local comparison →
residual adjacent unlocked local lane apply →
residual adjacent focused local validation →
residual adjacent focused validation activation-external handoff →
residual adjacent focused validation activation-external acceptance →
(optional) selected-step adjacent harness-eval.

Observed this run (digest `github-growth-20260713T185418.714620Z`,
`prop-skill-reverse-flow-continue` / reverse-flow bound against
`lingbol088-spec/reverse-flow-skill`, residual fortress/Hy3 adjacent):

- Reverse-flow focused validation remains `ready` / unrecorded (0/3) with
  `continue_plan.mode=run_pending` until supervisors follow continue dispatch
  policy and record/close body-free results; residual stages stay blocked waiting
  on reverse-flow record/close and activation-external acceptance
- Prior: residual acceptance packaging already collapses residual handoff into
  body-free residual activation-external acceptance readiness +
  keep_activation_external / note_remaining_residual_rows policy without
  residual_export
- New: `package_reverse_flow_focused_validation_continue_residual_cascade`
  collapses residual acceptance into body-free
  `residual_cascade_line` (for example
  `residual_cascade ready=true
  selected=prop-harness-fortress-local-eval status=complete progress=8/8
  blocked_at=none stages=open,entry,follow,comparison,unlocked_apply,
  focused_validation,handoff,acceptance remaining=0
  action=keep_activation_external residual_export=false
  next=keep_activation_external_after_residual_adjacent_focused_local_validation
  helper=package_reverse_flow_focused_validation_continue_residual_acceptance`)
  so supervisors do not re-derive residual cascade stage progress, blocked stage,
  remaining residual IDs, or keep_activation_external policy from eight nested
  residual cards
- New: follow and dispatch attach `residual_cascade`,
  `residual_cascade_line`, `residual_cascade_ready`,
  `residual_cascade_action`, `residual_cascade_progress_label`, and
  `residual_cascade_blocked_at`
- New: inventory-only wakes package blocked residual cascade
  (`ready=false`, `action=wait_for_reverse_flow`, `progress=0/8`,
  `blocked_at=open`, residual_export denied) for pre-exec audit while reverse-flow
  is still unrecorded
- New: operator_state exports nested `continue_residual_cascade`,
  `continue_residual_cascade_helper`,
  `continue_residual_cascade_line`,
  `continue_residual_cascade_ready`,
  `continue_residual_cascade_action`,
  `continue_residual_cascade_progress_label`, and
  `continue_residual_cascade_blocked_at` (alongside continue_residual_acceptance /
  continue_residual_handoff / continue_call_residual_acceptance /
  continue_residual_focused_validation / continue_residual_unlocked_apply /
  continue_residual_comparison / continue_residual_follow /
  continue_residual_entry / continue_residual_open / continue_finish_receipt /
  continue_finished)
- Ready/unrecorded residual cascade:
  `residual_cascade_ready=false`,
  `residual_cascade_action=wait_for_reverse_flow`,
  `residual_cascade_progress_label=0/8`, `residual_cascade_blocked_at=open`,
  residual_export denied; finish stays incomplete while progress is 0/N
- Full follow after reverse-flow pass + residual cascade: residual handoff becomes
  ready with `call_residual_acceptance=true`; residual acceptance then becomes
  ready/accepted with `action=keep_activation_external` (or
  `note_remaining_residual_rows` when remaining residual IDs exist); residual
  cascade then becomes ready/complete with `progress=8/8`, `blocked_at=none`,
  and the same keep_activation_external / note_remaining_residual_rows action;
  residual export still denied on continue/dispatch/follow/finish/residual_open/
  residual_entry/residual_follow/residual_comparison/residual_unlocked_apply/
  residual_focused_validation/residual_handoff/residual_acceptance/
  residual_cascade surfaces themselves (residual stages open only via residual
  pipeline helpers)
- While residual focused validation is ready/unrecorded after reverse-flow pass:
  residual handoff waits (`wait_for_residual_focused_validation`), residual
  acceptance waits (`wait_for_residual_handoff`), and residual cascade reports
  `blocked_at=handoff` with partial stage progress (for example 6/8) with
  residual_export denied
- Partial follow: runs remaining units only (`mode=record_remaining`) then
  packages keep_activation_external post_follow_through; residual unlocked apply,
  residual focused validation, and residual handoff become ready only when
  remaining units close, acceptance is accepted, residual queue is residual-active,
  residual comparison is residual-active ready, residual unlocked-apply criteria
  pass, residual focused-validation criteria pass, and residual handoff criteria pass
- Post-pass follow with recommendation still defaulted: action=`keep_activation_external`,
  call_dispatch_with_execute=false, does not re-run units; residual open, residual
  entry, residual follow, residual comparison, residual unlocked apply, residual
  focused validation, residual handoff, residual acceptance, and residual cascade
  stay ready (or cascade-progress legible) with residual_export denied when residual
  queue, residual apply, residual comparison, residual unlocked apply, residual
  focused validation, and residual handoff are ready
- Explicit `execute=False` on follow or dispatch stays inventory-only even when
  follow_through_action would be `execute_now`; residual open, residual entry,
  residual follow, residual comparison, residual unlocked apply, residual focused
  validation, residual handoff, residual acceptance, and residual cascade stay
  blocked while progress is 0/N
- While ready/unrecorded with zero partial rows:
  `continue_plan.mode=run_pending`,
  `supervisor_next_action=run_focused_local_test_validation_then_keep_activation_external`,
  pending work units list the full local command set; follow executes all
- While ready/unrecorded with partial rows:
  `continue_plan.mode=record_remaining`,
  pending work units shrink to remaining pairs only,
  `supervisor_next_action=record_remaining_reverse_flow_focused_validation_command_hashes_then_keep_activation_external`;
  follow executes remaining only
- After multi-wake merge covers expected hashes and record/close passes,
  continue_plan mode becomes `keep_activation_external`, pending work units
  clear, residual holds release when residual-active, finish receipt marks
  residual_queue ready, residual open packages residual next, residual entry
  packages selected residual, residual follow packages comparison policy,
  residual comparison packages unlocked-lane readiness, residual unlocked
  apply packages preferred test-first focused-validation policy, residual
  focused validation packages body-free command-hash progress plus
  activation-external handoff policy, residual handoff packages
  keep_activation_external plus remaining residual IDs and acceptance policy,
  residual acceptance packages keep_activation_external /
  note_remaining_residual_rows, and residual cascade packages stage progress
  (N/8), blocked_at, and the same keep_activation_external policy without
  enabling residual_export on continue surfaces
- Activation, push, promotion, provider launch, remote apply, external skill
  execution, and kernel restart stay denied
- agent-chief remains privacy review-only

Pipeline stages remain the three classifier stages plus post-completion unlock,
focused validation, result recording/close, activation-external handoff,
acceptance, residual adjacent queue, residual harness-eval local apply,
residual harness-eval local comparison, residual unlocked local lane apply,
residual focused local validation, residual activation-external handoff, and
residual activation-external acceptance:

1. classifier — skill_route_discovery vs agent_harness_eval_required vs privacy/offensive review-only
2. route_profiles — reverse-flow → `codex_workflow_gate` + `skill_route_discovery_first`; rnskill →
   `generic_skill_workflow`
3. bounded_local_apply_lanes — reverse-flow prefers `test`, rnskill prefers `documentation`; only
   documentation/config/test/code_patch; local comparison required before unlock; `runtime_action=none`
4. unlocked apply — when completion is complete and reverse-flow `test` is unlocked, emit
   `skill_route_discovery_unlocked_local_test_lane_apply` and keep activation external
5. focused validation — emit
   `skill_route_discovery_focused_local_test_validation`; schedule body-free
   command hashes; residual hold until recorded; never activate from this surface
6. result recording / close — close `ready` → `passed`/`failed` via pipeline results,
   `record_skill_route_discovery_focused_local_test_validation_results`, or
   `close_skill_route_discovery_focused_local_test_validation_with_outcome`
7. activation-external handoff — on recorded pass emit
   `skill_route_discovery_focused_validation_activation_external_handoff`; keep
   push/promotion/restart external
8. activation-external acceptance — on ready handoff emit
   `skill_route_discovery_focused_validation_activation_external_acceptance`; still
   non-activating
9. residual adjacent queue — on accepted package with residual fortress/Hy3 IDs emit
   `skill_route_discovery_focused_validation_residual_adjacent_queue`; package IDs
   without skill unlock inheritance
10. residual harness-eval local apply — on ready residual queue emit
    `skill_route_discovery_residual_adjacent_harness_eval_local_apply`; select one
    residual row and hand off to `agent_harness_eval_cluster_local_apply`
11. residual harness-eval local comparison — on ready residual local apply emit
    `skill_route_discovery_residual_adjacent_harness_eval_local_comparison`; unlock
    documentation/test/code_patch after harness criteria pass
12. residual unlocked local lane apply — on ready residual harness comparison emit
    `skill_route_discovery_residual_adjacent_unlocked_local_lane_apply`; package
    preferred test-first focused validation without skill unlock inheritance
13. residual focused local validation — on ready residual unlocked apply emit
    `skill_route_discovery_residual_adjacent_focused_local_validation`; record
    body-free command-hash results for the residual selected lane without skill
    unlock inheritance
14. residual activation-external handoff — on residual focused validation pass emit
    `skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`;
    package keep_activation_external and note remaining residual rows without skill
    unlock inheritance
15. residual activation-external acceptance — on ready residual handoff emit
    `skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`;
    accept keep_activation_external and note remaining residual rows without skill
    unlock inheritance
16. selected-step adjacent residual — fortress-style selected rows stay available for
    agent harness-eval handoff; skill unlocks stay closed

External skill execution, provider launch, remote apply, push, promotion, and restart stay denied.
Prefer collapsing residual acceptance into residual cascade stage progress over
re-inspecting eight nested residual cards after residual acceptance is accepted.
Do not advance residual fortress stages until reverse-flow focused validation is
recorded/closed and activation-external acceptance completes.

## Upstream Evidence Habit

Previous theme (`upstream-evidence-capability`, complete): mixed public agent signals became
`upstream_evidence_capability_step` → `agent_harness_eval_cluster` →
`agent_harness_eval_cluster_local_apply` → `agent_harness_eval_cluster_local_apply_completion`. That pattern is
the template the skill-route pipeline followed: one operator-visible capability path, body-free exports, narrow
safety boundary, and a final local-apply completion handoff. Residual adjacent focused validation
activation-external acceptance is the skill-route residual analogue of “after residual fortress/Hy3 focused
validation activation-external handoff is ready, accept keep_activation_external without inheriting reverse-flow skill
unlocks and note any remaining residual rows.”
