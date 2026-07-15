# Architecture

## Objective

Build an agent that periodically tracks public GitHub trends and converts them into useful, rollback-backed local improvements. The agent should learn from the broader ecosystem while leaving enough artifacts to audit and recover its autonomous changes.

## Components

### Native Supervisor

Runs the intake job once per hour by launching a fresh one-shot child process in an isolated candidate worktree. It owns wake cadence, heartbeat artifacts, pass records, candidate worktree cleanup, health-gated promotion, restart requests, and optional pushes for successful autonomous source changes. It should never assume the previous run completed successfully unless the digest and pass record were persisted.

Repository-native command:

```text
blackhole-supervisor --repo-path . --interval-seconds 3600
```

Alternative choices:

- GitHub Actions or another hourly scheduler for a read-only trend scanner.
- Serverless timer for broader public trend monitoring.

### GitHub Intake

Discovers recently created public repositories that are gaining attention, then reads recent events for those repositories. A manual repository list remains available for debugging and narrow experiments.

Trend discovery uses GitHub repository search with bounded query parameters:

- creation window
- minimum stars
- optional search terms such as `topic:ai` or `language:Python`
- sort by stars, forks, or updated time
- fork inclusion policy

The digest should keep a trend snapshot with star count, first-seen status, and star delta since the previous run.

Initial event types:

- commits
- pull requests
- issues
- releases
- workflow runs

The intake should normalize each item into a compact event envelope with source URL, timestamp, actor, repo, event kind, title, summary, changed paths, labels, and raw relevance hints.

### Relevance Filter

Scores events by:

- subject match
- touched paths
- failure/success signal
- dependency/API changes
- repeated patterns
- relationship to known work
- memory bias from historically useful repositories and topics

The filter must explain why an event was selected or ignored.

### Memory Layer

Stores lightweight cross-run learning in `memory.json`, separate from cursor state.

The memory tracks:

- repository stats: seen count, useful signal count, validation count, failure count, last seen time
- topic stats: seen count, useful signal count, validation count, failure count, last seen time
- lessons: proposal ID, source digest, summary, evidence, outcome
- theme window: the active multi-pass capability slice, planned pass count, anchoring proposals, and evidence URLs

This layer is intentionally small and transparent. It biases proposal ordering toward sources and topics that have produced useful lessons before, and it gives consecutive self-evolution passes a shared capability target. It can be deleted without corrupting cursor state.

### Self-Model Layer

Stores a tracked, revisable self-description in `docs/self-model.md`. The file starts nearly blank on purpose: it gives the agent a place to write, rename, remove, contradict, or leave empty its own categories over time.

The self-model is not a permissions document. It cannot authorize new tools, remote writes, sandbox bypasses, or promotion behavior. Every self-evolution task receives a before-run snapshot of the file and may edit the file directly when that edit is justified by the run's evidence and validation plan.

The controller writes self-model snapshots beside growth artifacts so a run can be replayed:

- `latest-self-model-before.json`
- `latest-self-model-after.json`
- `latest-self-model.json`

### Learning Digest

Writes a bounded hourly digest:

- new facts
- reusable implementation patterns
- risks or regressions
- candidate actions
- evidence links
- confidence and urgency

The digest should be small enough for agents and operators to replay.

### Proposal Generator

Turns high-value digest entries into candidate improvements or local application tasks:

- documentation update
- test addition
- config change
- code patch draft
- follow-up issue
- "do nothing" decision

The default output is a local proposal that can be applied autonomously by the Codex kernel on an evolution branch.

Proposal generation has two layers:

- `hybrid`: the default enhanced path that asks an LLM to turn the frozen digest, memory context, and self-model snapshot into candidate growth routes before deterministic safety checks finalize proposals.
- `heuristic`: an explicit conservative path that ranks signals and renders rule-based proposals without the interpretation layer.
- `llm`: an interpretation-only proposal path that skips heuristic proposal fill-in after accepted LLM candidates.

The LLM interpretation layer is not an authority. It cannot add evidence URLs, remove rule risk flags, decide final validation gates, or grant permissions. Deterministic safety review is narrow: offensive behavior and privacy leakage remain review-gated, while other locally validated behavior changes may proceed when runtime configuration provides the needed capability. If the JSON output is invalid, cites unknown evidence, exceeds proposal limits, or fails safety review, the controller writes `latest-llm-proposal-review.json` and falls back to heuristic proposals.

When `max_items` truncates digest evidence, the frozen package records selected item IDs, truncated item IDs, selection diagnostics, and metadata-only uncertainty counts. Interpreters may cite only selected `item_id` values present in `items`; they must not add URLs or treat truncated item IDs as evidence. If a PR-heavy stream is mostly generic, untitled, or omitted by truncation, proposal uncertainty should say that PR-specific details were not available. Duplicate proposal IDs, and duplicate proposal kind plus evidence-ref shapes, are rejected during deterministic review.

Public agent-project movement follows the same rule: it is a source of bounded
local validation candidates, not permission or implementation authority. See
`docs/upstream-evidence-interpretation.md` for the evidence citation, missing
detail, low-detail PR/push interpretation rule, and validation-lane contract.
Skill repository discoveries use the classification-only matrix in
`docs/skill-route-discovery.md` before any local activation path is considered.

### Capability Theme Window

Before a self-evolution task is rendered, the controller derives a small `capability_theme_window` from the active proposals and persisted growth memory. The default window spans four planned passes. While the window is active, later passes carry the same theme into the Codex task even when a new digest contains tempting unrelated micro-patches.

The window is not a permission source and does not override safety review. It is continuity pressure: each pass should deepen the same capability slice with behavior, controller surfaces, recovery workflows, tests, and docs until the window completes or the evidence shows the theme is exhausted or unsafe. The current window is written into `memory.json`, `latest.json`, `latest-self-evolution-plan.json`, the plan markdown, and the self-evolution manifest.

For the `skill-route-discovery` theme, digests also emit
`skill_route_discovery_capability_pipeline`: one operator-visible local pipeline
with stages `classifier` → `route_profiles` → `bounded_local_apply_lanes`.
Pass 1 translates reverse-flow-skill and rnskill skill-workflow trend signals
into that pipeline rather than isolated notes. reverse-flow-skill maps to
`codex_workflow_gate` with `skill_route_discovery_first` and a preferred local
`test` lane; rnskill maps to `generic_skill_workflow` with a preferred
`documentation` lane. Allowed lanes stay limited to documentation, config,
test, or code_patch. Local comparison is required before any lane unlock.
Pass 2 evaluates `skill_route_discovery_local_comparison` criteria against the
reverse-flow probe and exposes
`skill_route_discovery_reverse_flow_test_validation_lane` so the preferred
`test` lane unlocks only after pipeline-stage comparison; companion rnskill
rows remain documentation-preferring profiles on the same path.
Pass 3 packages the unlocked reverse-flow lane into
`skill_route_discovery_local_apply` with
`skill_route_discovery_rnskill_docs_validation_lane` (body-free documentation
companion) and `skill_route_discovery_config_gate_boundary` (keeps
general-agent and privacy rows out of skill unlocks) on the same pipeline.
Pass 4 closes the theme with
`skill_route_discovery_local_apply_completion` once reverse-flow local apply is
ready: it binds the full capability pipeline, unlocked local `test` lane,
retained privacy and general-agent boundaries, and the external supervisor next
action (`apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external`).
After completion, `skill_route_discovery_unlocked_local_test_lane_apply`
packages that supervisor action into a body-free focused local test validation
apply for reverse-flow (`prop-skill-reverse-flow-test-lane`) while keeping
activation external. When that apply is ready,
`skill_route_discovery_focused_local_test_validation` records body-free
command-hash results (`ready` → `passed`/`failed`) and keeps activation
external. Supervisors close results via
`focused_validation_command_results` on the pipeline builder or
`record_skill_route_discovery_focused_local_test_validation_results` on an
existing packet (`prop-skill-reverse-flow-focused-test-validation`). Partial
body-free rows accumulate across record wakes via
`merge_skill_route_discovery_focused_validation_command_results`; operator_state
exports recorded/missing expected hashes, pending command texts/counts, pending
work unit pairs (command + hash), and `continue_plan` mode body-free until
coverage is complete.
`build_reverse_flow_focused_validation_continue_plan` unifies zero-row first
wakes (`mode=run_pending`) and multi-wake partial continue
(`mode=record_remaining`) around `pending_work_units` plus `pending_commands`,
and while partial `supervisor_next_action` promotes to
`record_remaining_reverse_flow_focused_validation_command_hashes_then_keep_activation_external`
via `resolve_reverse_flow_focused_validation_continue_supervisor_next` (not a
full focused re-run). Supervisors may record only pending units through
`record_reverse_flow_focused_validation_continue_outcomes` after
`materialize_reverse_flow_focused_validation_continue_record_rows`, or run and
record them through
`run_reverse_flow_focused_validation_continue_pending_work_units` (local pytest
inventory allowlist via
`build_reverse_flow_focused_validation_continue_run_plan` +
`execute_reverse_flow_focused_validation_continue_run_plan`; no stdout export,
no activation). After inventory or run/record,
`resolve_reverse_flow_focused_validation_continue_run_supervisor_wake` packages
reverse-flow-first `supervisor_next` and residual-hold state so residual
fortress stages stay blocked until reverse-flow record/close and
activation-external acceptance.
`package_reverse_flow_focused_validation_continue_dispatch_inventory` packages a
body-free inventory dispatch packet (`action`, `execute_recommended`, residual
hold) without running commands.
`resolve_reverse_flow_focused_validation_continue_dispatch_follow_through`
collapses that inventory into `follow_through_action`
(`execute_now` | `wait_for_local_allowlist` | `keep_activation_external` |
`repair` | `noop`) and `call_dispatch_with_execute`.
`package_reverse_flow_focused_validation_continue_operator_card` collapses
progress (`progress_label` such as `0/3`), follow-through policy, preferred
helper, residual hold, `supervisor_next`, and a body-free `action_line` into one
operator card.
`package_reverse_flow_focused_validation_continue_progress_transition` collapses
pre/post operator cards into `progress_transition_label` (for example
`0/3→3/3`), `progress_advanced`, `follow_through_transition`, `recorded_delta`,
and `transition_line` so supervisors do not compare nested progress labels after
continue wakes.
`package_reverse_flow_focused_validation_continue_exec_receipt` collapses
continue-run plan/result into body-free `exec_line` (for example
`exec mode=run_pending ran=3 passed=3 failed=0 skipped=0 recorded=true`) and
`exec_plan_line` so supervisors do not re-derive nested `unit_results` after
execute wakes; stdout stays unexported and residual export stays denied.
`package_reverse_flow_focused_validation_continue_finish_receipt` collapses
post-continue progress, focused status, handoff/acceptance, and residual hold
into body-free `finish_line` (for example
`finish complete=true progress=3/3 status=passed mode=keep_activation_external
handoff=ready acceptance=accepted residual_hold=false residual_queue=ready
residual_export=false`) plus `continue_finished` / `residual_queue_ready` so
supervisors do not re-derive nested post cards after reverse-flow continue
finishes. Residual export stays denied on continue surfaces even when
`residual_queue_ready` is true.
`package_reverse_flow_focused_validation_continue_residual_open` collapses
finish `residual_queue_ready` plus
`focused_validation_residual_adjacent_queue` into body-free `residual_open_line`
(for example `residual_open ready=true count=1 status=ready
next=hand_off_residual_adjacent_rows_to_agent_harness_eval_cluster_local_apply
residual_export=false
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_apply`)
plus `residual_open` / `residual_adjacent_count` so residual pipeline entry is
legible without nested residual-queue re-assembly. Residual export stays denied
on continue surfaces even when residual open is ready.
`package_reverse_flow_focused_validation_continue_residual_entry` collapses
residual open plus residual adjacent harness-eval local apply selection into
body-free `residual_entry_line` (for example
`residual_entry ready=true selected=prop-harness-fortress-local-eval
status=ready count=1
next=run_agent_harness_eval_local_comparison_for_residual_adjacent_row
residual_export=false
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_apply`)
plus `residual_entry` / `selected_residual_proposal_id` so residual selection is
legible without nested residual-apply re-assembly. Residual export stays denied
on continue surfaces even when residual entry is ready; selected residual IDs
stay empty while residual open is blocked (reverse-flow-waiting selection hold).
`package_reverse_flow_focused_validation_continue_residual_follow` collapses
residual entry into body-free `residual_follow_line` (for example
`residual_follow ready=true selected=prop-harness-fortress-local-eval
action=open_residual_harness_eval_local_comparison call_comparison=true
residual_export=false
next=run_agent_harness_eval_local_comparison_for_residual_adjacent_row
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`)
plus `residual_follow` / `residual_follow_action` /
`call_residual_comparison` so residual comparison follow-through is legible
without nested residual-entry re-assembly. Residual export stays denied on
continue surfaces even when residual follow is ready; `call_residual_comparison`
is informational policy only (residual stages open via residual pipeline helpers).
`package_reverse_flow_focused_validation_continue_residual_comparison` collapses
residual follow into body-free `residual_comparison_line` (for example
`residual_comparison ready=true selected=prop-harness-fortress-local-eval
status=ready comparison=passed_local_comparison unlocked=documentation,test,code_patch
action=open_residual_unlocked_local_lane_apply call_unlocked_apply=true
residual_export=false
next=apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external
helper=build_skill_route_discovery_residual_adjacent_harness_eval_local_comparison`)
plus `residual_comparison` / `residual_comparison_action` /
`call_residual_unlocked_apply` so residual comparison readiness and unlocked-lane
policy are legible without nested residual-follow / comparison re-assembly.
Residual export stays denied on continue surfaces even when residual comparison
is ready; `call_residual_unlocked_apply` is informational policy only (residual
stages open via residual pipeline helpers).
`package_reverse_flow_focused_validation_continue_residual_unlocked_apply`
collapses residual comparison into body-free `residual_unlocked_apply_line` (for
example `residual_unlocked_apply ready=true selected=prop-harness-fortress-local-eval
status=ready lane=test preferred=test unlocked=documentation,test,code_patch
comparison_ready=true action=open_residual_focused_local_validation
call_focused_validation=true residual_export=false
next=run_focused_local_validation_for_residual_adjacent_unlocked_lane_and_keep_activation_external
helper=build_skill_route_discovery_residual_adjacent_unlocked_local_lane_apply`)
plus `residual_unlocked_apply` / `residual_unlocked_apply_action` /
`call_residual_focused_validation` so residual unlocked-apply readiness and
preferred test-first focused-validation policy are legible without nested
residual-comparison / unlocked-apply re-assembly. Residual export stays denied
on continue surfaces even when residual unlocked apply is ready;
`call_residual_focused_validation` is informational policy only (residual stages
open via residual pipeline helpers).
`package_reverse_flow_focused_validation_continue_residual_focused_validation`
collapses residual unlocked apply into body-free
`residual_focused_validation_line` (for example
`residual_focused_validation ready=true selected=prop-harness-fortress-local-eval
status=ready lane=test preferred=test progress=0/3 unlocked_apply_ready=true
action=run_residual_focused_validation call_handoff=false residual_export=false
next=run_focused_local_validation_for_residual_adjacent_unlocked_lane_and_keep_activation_external
helper=build_skill_route_discovery_residual_adjacent_focused_local_validation`)
plus `residual_focused_validation` / `residual_focused_validation_action` /
`call_residual_handoff` so residual focused-validation readiness, body-free
command-hash progress, and activation-external handoff policy are legible
without nested residual-unlocked-apply / focused-validation re-assembly.
Residual export stays denied on continue surfaces even when residual focused
validation is ready; `call_residual_handoff` is informational policy only
(true only after residual focused validation records a pass).
`package_reverse_flow_focused_validation_continue_residual_handoff`
collapses residual focused validation into body-free
`residual_handoff_line` (for example
`residual_handoff ready=true selected=prop-harness-fortress-local-eval
status=ready lane=test preferred=test remaining=0 focused_ready=true
action=open_residual_activation_external_acceptance call_acceptance=true
residual_export=false
next=keep_activation_external_after_residual_adjacent_focused_local_validation
helper=build_skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`)
plus `residual_handoff` / `residual_handoff_action` /
`call_residual_acceptance` so residual activation-external handoff readiness,
remaining residual IDs, and acceptance policy are legible without nested
residual-focused-validation / handoff re-assembly. Residual export stays denied
on continue surfaces even when residual handoff is ready;
`call_residual_acceptance` is informational policy only (true only after residual
handoff is ready).
`package_reverse_flow_focused_validation_continue_residual_acceptance`
collapses residual handoff into body-free
`residual_acceptance_line` (for example
`residual_acceptance ready=true selected=prop-harness-fortress-local-eval
status=accepted lane=test preferred=test remaining=0 handoff_ready=true
action=keep_activation_external residual_export=false
next=keep_activation_external_after_residual_adjacent_focused_local_validation
helper=build_skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`)
plus `residual_acceptance` / `residual_acceptance_action` so residual
activation-external acceptance readiness, remaining residual IDs, and
keep_activation_external policy are legible without nested residual-handoff /
acceptance re-assembly. Residual export stays denied on continue surfaces even
when residual acceptance is accepted.
`package_reverse_flow_focused_validation_continue_residual_cascade`
collapses residual acceptance into body-free
`residual_cascade_line` (for example
`residual_cascade ready=true selected=prop-harness-fortress-local-eval
status=complete progress=8/8 blocked_at=none stages=open,entry,follow,
comparison,unlocked_apply,focused_validation,handoff,acceptance remaining=0
action=keep_activation_external residual_export=false
next=keep_activation_external_after_residual_adjacent_focused_local_validation
helper=package_reverse_flow_focused_validation_continue_residual_acceptance`)
plus `residual_cascade` / `residual_cascade_action` /
`residual_cascade_progress_label` / `residual_cascade_blocked_at` so residual
cascade stage progress, blocked stage, remaining residual IDs, and
keep_activation_external policy are legible without nested residual-acceptance
/ stage re-assembly. Residual export stays denied on continue surfaces even
when residual cascade is complete.
`package_reverse_flow_focused_validation_continue_cascade`
collapses reverse-flow continue progress plus residual cascade into body-free
`continue_cascade_line` (for example
`continue_cascade ready=false reverse_progress=0/3 residual_progress=0/8
residual_blocked_at=open reverse_action=execute_now
residual_action=wait_for_reverse_flow action=execute_now call_execute=true
residual_export=false
next=run_focused_local_test_validation_then_keep_activation_external
helper=follow_reverse_flow_focused_validation_continue_dispatch`)
plus `continue_cascade` / `continue_cascade_action` /
`continue_cascade_reverse_progress_label` /
`continue_cascade_residual_progress_label` /
`continue_cascade_residual_blocked_at` so reverse-flow progress, residual
cascade progress/blocked_at, and reverse-flow-first next action are legible
without nested action_line + residual_cascade_line re-assembly. Residual
export stays denied on continue surfaces even when continue cascade is complete.
`package_reverse_flow_focused_validation_continue_cascade_transition`
collapses pre/post continue_cascade packages into body-free
`continue_cascade_transition_line` (for example
`continue_cascade_transition reverse=0/3→3/3 residual=0/8→0/8
blocked_at=open→open action=execute_now→keep_activation_external
reverse_advanced=true residual_advanced=false cascade_advanced=true
ready=false→false executed=true recorded=true residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_cascade_transition`)
plus nested `continue_cascade_transition` / `continue_cascade_transition_line` /
`continue_cascade_advanced` / `continue_cascade_reverse_progress_transition` /
`continue_cascade_residual_progress_transition` so reverse-flow progress,
residual cascade progress/blocked_at, and cascade action transitions are
legible after continue wakes without nested pre/post comparison. Residual
export stays denied on continue surfaces even when reverse progress completes.
`package_reverse_flow_focused_validation_continue_cascade_wake`
collapses continue_cascade_transition plus exec_receipt, finish_receipt, and
residual_open into body-free `continue_cascade_wake_line` with classified
`wake_outcome` (for example
`continue_cascade_wake outcome=reverse_complete reverse=0/3→3/3
residual=0/8→0/8 cascade_advanced=true executed=true recorded=true
finished=true residual_open=false residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_cascade_wake`)
plus nested `continue_cascade_wake` / `continue_cascade_wake_line` /
`continue_cascade_wake_outcome` so supervisors pin one wake outcome enum
instead of re-assembling cascade_transition + exec + finish + residual_open.
Residual export stays denied on continue surfaces even when residual_open
becomes ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route`
collapses continue_cascade_wake into body-free
`continue_cascade_wake_route_line` with classified `route_action` (for example
`continue_cascade_wake_route outcome=execute_recommended action=execute_now
call_execute=true residual_route=false reverse=0/3→0/3 residual=0/8→0/8
residual_export=false
next=run_focused_local_test_validation_then_keep_activation_external
helper=follow_reverse_flow_focused_validation_continue_dispatch
route_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route`)
plus nested `continue_cascade_wake_route` / `continue_cascade_wake_route_line` /
`continue_cascade_wake_route_action` /
`continue_cascade_wake_route_call_execute` so supervisors pin one route action
enum and preferred helper instead of re-assembling wake_outcome + follow
policy. Residual export stays denied on continue surfaces even when residual
route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply`
collapses pre/post continue_cascade_wake_route into body-free
`continue_cascade_wake_route_apply_line` with pre→post route action transition
(for example
`continue_cascade_wake_route_apply pre_action=execute_now
post_action=keep_activation_external
action=execute_now→keep_activation_external route_advanced=true
call_execute=true→false residual_route=false→false reverse=0/3→3/3
residual=0/8→0/8 executed=true recorded=true residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply`)
plus nested `continue_cascade_wake_route_apply` /
`continue_cascade_wake_route_apply_line` /
`continue_cascade_wake_route_action_transition` /
`continue_cascade_wake_route_advanced` so supervisors pin one apply receipt
instead of re-comparing nested route packets after continue wakes. Residual
export stays denied on continue surfaces even when residual route opens after
residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow`
collapses continue_cascade_wake_route_apply into body-free
`continue_cascade_wake_route_apply_follow_line` with applied route → preferred
helper (for example
`continue_cascade_wake_route_apply_follow applied=keep_activation_external
advanced=true executed=true recorded=true call_execute=false
residual_route=false reverse=0/3→3/3 residual=0/8→0/8 residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
apply_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply`)
plus nested `continue_cascade_wake_route_apply_follow` /
`continue_cascade_wake_route_apply_follow_line` /
`continue_cascade_wake_route_apply_follow_action` /
`continue_cascade_wake_route_apply_follow_preferred_helper` /
`continue_cascade_wake_route_apply_follow_call_execute` so supervisors pin one
follow receipt instead of re-mapping applied route actions after continue
wakes. Residual export stays denied on continue surfaces even when residual
route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin`
collapses continue_cascade_wake_route_apply_follow into body-free
`continue_cascade_wake_route_apply_follow_pin_line` with classified pin mode
(for example
`continue_cascade_wake_route_apply_follow_pin action=execute_now
mode=execute_helper call_execute=true pin_ready=true residual_route=false
reverse=0/3→0/3 residual=0/8→0/8 residual_export=false
next=run_focused_local_test_validation_then_keep_activation_external
helper=follow_reverse_flow_focused_validation_continue_dispatch
follow_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow`)
plus nested `continue_cascade_wake_route_apply_follow_pin` /
`continue_cascade_wake_route_apply_follow_pin_line` /
`continue_cascade_wake_route_apply_follow_pin_action` /
`continue_cascade_wake_route_apply_follow_pin_mode` /
`continue_cascade_wake_route_apply_follow_pin_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_ready` so supervisors pin one
call recipe (`execute_helper` / `package_helper` / `inventory_only`) instead of
re-deriving execute vs package policy after continue wakes. Residual export
stays denied on continue surfaces even when residual route opens after
residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin into body-free
`continue_cascade_wake_route_apply_follow_pin_call_line` with pre→post pin
action/mode transition (for example
`continue_cascade_wake_route_apply_follow_pin_call pre_action=execute_now
post_action=keep_activation_external action=execute_now→keep_activation_external
mode=execute_helper→package_helper call_execute=true→false pin_advanced=true
pin_ready=true→true residual_route=false→false reverse=0/3→3/3 residual=0/8→0/8
executed=true recorded=true residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin`)
plus nested `continue_cascade_wake_route_apply_follow_pin_call` /
`continue_cascade_wake_route_apply_follow_pin_call_line` /
`continue_cascade_wake_route_apply_follow_pin_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_mode_transition` /
`continue_cascade_wake_route_apply_follow_pin_advanced` so supervisors pin one
call receipt instead of re-comparing nested pin packets after continue wakes.
Residual export stays denied on continue surfaces even when residual route
opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next`
seals continue_cascade_wake_route_apply_follow_pin_call into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_line` with next invoke
policy (for example
`continue_cascade_wake_route_apply_follow_pin_call_next
action=keep_activation_external mode=package_helper invoke=package_helper
advanced=true call_execute=false next_ready=true residual_route=false
reverse=0/3→3/3 residual=0/8→0/8 residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call`)
plus nested `continue_cascade_wake_route_apply_follow_pin_call_next` /
`continue_cascade_wake_route_apply_follow_pin_call_next_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_invoke` /
`continue_cascade_wake_route_apply_follow_pin_call_next_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_ready` so supervisors
pin one next-invoke recipe instead of re-deriving execute vs package policy
from nested pin_call transitions after continue wakes. Residual export stays
denied on continue surfaces even when residual route opens after
residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin_call_next into
body-free `continue_cascade_wake_route_apply_follow_pin_call_next_call_line`
with pre→post next action/invoke transition (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call
pre_action=execute_now post_action=keep_activation_external
action=execute_now→keep_activation_external
invoke=execute_helper→package_helper call_execute=true→false
next_advanced=true next_ready=true→true residual_route=false→false
reverse=0/3→3/3 residual=0/8→0/8 executed=true recorded=true
residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_next_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next`)
plus nested `continue_cascade_wake_route_apply_follow_pin_call_next_call` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_invoke_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_advanced` so supervisors
pin one next-call receipt instead of re-comparing nested pin_call_next packets
after continue wakes. Residual export stays denied on continue surfaces even
when residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow`
maps continue_cascade_wake_route_apply_follow_pin_call_next_call into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_line` with
applied next → preferred helper (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow
applied=keep_activation_external invoke=package_helper mode=package_helper
advanced=true call_execute=false follow_ready=true residual_route=false
reverse=0/3→3/3 residual=0/8→0/8 executed=true recorded=true
residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
next_call_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call`)
plus nested `continue_cascade_wake_route_apply_follow_pin_call_next_call_follow` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_mode` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_ready` so
supervisors pin one next-call follow receipt instead of re-mapping applied next
action/invoke after continue wakes. Residual export stays denied on continue
surfaces even when residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin`
collapses continue_cascade_wake_route_apply_follow_pin_call_next_call_follow into
body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_line` with
classified pin mode (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin
action=execute_now mode=execute_helper call_execute=true pin_ready=true
residual_route=false reverse=0/3→0/3 residual=0/8→0/8 residual_export=false
next=run_focused_local_test_validation_then_keep_activation_external
helper=follow_reverse_flow_focused_validation_continue_dispatch
follow_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow`)
plus nested `continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_mode` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_ready` so
supervisors pin one call recipe instead of re-deriving execute vs package policy
after continue wakes. Residual export stays denied on continue surfaces even when
residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_line`
with pre→post pin action/mode transition (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call
pre_action=execute_now post_action=keep_activation_external
action=execute_now→keep_activation_external mode=execute_helper→package_helper
call_execute=true→false pin_advanced=true pin_ready=true→true
residual_route=false→false reverse=0/3→3/3 residual=0/8→0/8 executed=true
recorded=true residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_mode_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_advanced` so
supervisors pin one call receipt instead of re-comparing nested pin packets after
continue wakes. Residual export stays denied on continue surfaces even when residual
route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next`
seals continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_line`
with sealed next invoke policy (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next
action=keep_activation_external mode=package_helper invoke=package_helper
advanced=true call_execute=false next_ready=true residual_route=false
reverse=0/3→3/3 residual=0/8→0/8 residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_invoke` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_ready` so
supervisors pin one next-invoke recipe instead of re-deriving execute vs package
policy from nested pin_call transitions after continue wakes. Residual export stays
denied on continue surfaces even when residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_line`
with pre→post next action/invoke transition (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call
pre_action=execute_now post_action=keep_activation_external
action=execute_now→keep_activation_external
invoke=execute_helper→package_helper call_execute=true→false
next_advanced=true next_ready=true→true residual_route=false→false
reverse=0/3→3/3 residual=0/8→0/8 executed=true recorded=true
residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_next_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_invoke_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_advanced` so
supervisors pin one next-call receipt instead of re-comparing nested pin_call_next
packets after continue wakes. Residual export stays denied on continue surfaces even
when residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow`
maps continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_line`
with applied next → preferred helper (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow
applied=keep_activation_external invoke=package_helper mode=package_helper
advanced=true call_execute=false follow_ready=true residual_route=false
reverse=0/3→3/3 residual=0/8→0/8 executed=true recorded=true
residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
next_call_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_mode` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_ready` so
supervisors pin one deep next-call follow receipt instead of re-mapping applied next
action/invoke after continue wakes. Residual export stays denied on continue surfaces
even when residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin`
maps continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_line`
with classified pin mode from the deep next_call_follow receipt (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin
action=execute_now mode=execute_helper call_execute=true pin_ready=true
advanced=false residual_route=false reverse=0/3→0/3 residual=0/8→0/8
residual_export=false
next=run_focused_local_test_validation_then_keep_activation_external
helper=follow_reverse_flow_focused_validation_continue_dispatch
follow_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_mode` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_ready` so
supervisors pin one deep call recipe instead of re-deriving execute vs package policy
after continue wakes. Residual export stays denied on continue surfaces even when
residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_line`
with pre→post pin action/mode transition (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call
pre_action=execute_now post_action=keep_activation_external
action=execute_now→keep_activation_external mode=execute_helper→package_helper
call_execute=true→false pin_advanced=true pin_ready=true→true
residual_route=false→false reverse=0/3→3/3 residual=0/8→0/8 executed=true
recorded=true residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_mode_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_advanced` so
supervisors pin one deep call receipt instead of re-comparing nested deep pin packets
after continue wakes. Residual export stays denied on continue surfaces even when
residual route opens after residual_open_ready.
`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next`
seals continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_line`
with next invoke policy (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next
action=keep_activation_external mode=package_helper invoke=package_helper
advanced=true call_execute=false next_ready=true residual_route=false
reverse=0/3→3/3 residual=0/8→0/8 residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call`)
plus nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_action` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_invoke` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_preferred_helper` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call_execute` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_ready` so
supervisors pin one deep next-invoke recipe instead of re-deriving execute vs package
policy from nested deep pin_call transitions after continue wakes. Residual export
stays denied on continue surfaces even when residual route opens after residual_open_ready.
Preferred
policy-aware operator entry is
`follow_reverse_flow_focused_validation_continue_dispatch`
(inventory → follow-through → dispatch execute only when recommended, with
`post_follow_through`, `operator_card` / `post_operator_card`,
`progress_transition`, `exec_receipt`, `finish_receipt`, `residual_open`,
`residual_entry`, `residual_follow`, `residual_comparison`,
`residual_unlocked_apply`, `residual_focused_validation`, `residual_handoff`,
`residual_acceptance`, `residual_cascade`, `continue_cascade`,
`continue_cascade_transition`, `continue_cascade_wake`,
`continue_cascade_wake_route`, `continue_cascade_wake_route_apply`,
`continue_cascade_wake_route_apply_follow`,
`continue_cascade_wake_route_apply_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next`, and
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call` after
run/record).
Low-level single operator entry remains
`dispatch_reverse_flow_focused_validation_continue_supervisor_wake` (inventory
packet, optional allowlisted run/record when executable, always reverse-flow-first
`supervisor_wake` plus `post_dispatch_inventory`, `follow_through`, operator
card progress labels, `progress_transition`, `exec_receipt`, `finish_receipt`,
`residual_open`, `residual_entry`, `residual_follow`, `residual_comparison`,
`residual_unlocked_apply`, `residual_focused_validation`, `residual_handoff`,
`residual_acceptance`, `residual_cascade`, `continue_cascade`,
`continue_cascade_transition`, `continue_cascade_wake`,
`continue_cascade_wake_route`, `continue_cascade_wake_route_apply`,
`continue_cascade_wake_route_apply_follow`,
`continue_cascade_wake_route_apply_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call`, and
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next`; residual
export stays denied on the dispatch surface).
Durable `operator_state` also exports
`continue_run_recommended`, inventory `continue_supervisor_wake`, nested
`continue_dispatch`, `continue_dispatch_action`,
`continue_dispatch_execute_recommended`, nested
`continue_dispatch_follow_through`, `continue_dispatch_follow_through_action`,
`continue_dispatch_call_with_execute`, `continue_dispatch_helper`,
`continue_dispatch_inventory_helper`,
`continue_dispatch_follow_through_helper`, nested
`continue_operator_card`, `continue_operator_card_helper`,
`continue_progress_label`, `continue_action_line`,
`continue_progress_transition_helper`, `continue_exec_receipt_helper`,
nested `continue_finish_receipt`, `continue_finish_receipt_helper`,
`continue_finish_line`, `continue_finished`,
`continue_residual_queue_ready`, nested `continue_residual_open`,
`continue_residual_open_helper`, `continue_residual_open_line`,
`continue_residual_open_ready`, `continue_residual_adjacent_count`, nested
`continue_residual_entry`, `continue_residual_entry_helper`,
`continue_residual_entry_line`, `continue_residual_entry_ready`,
`continue_selected_residual_proposal_id`, nested `continue_residual_follow`,
`continue_residual_follow_helper`, `continue_residual_follow_line`,
`continue_residual_follow_ready`, `continue_residual_follow_action`,
`continue_call_residual_comparison`, nested `continue_residual_comparison`,
`continue_residual_comparison_helper`, `continue_residual_comparison_line`,
`continue_residual_comparison_ready`, `continue_residual_comparison_action`,
`continue_call_residual_unlocked_apply`, nested
`continue_residual_unlocked_apply`, `continue_residual_unlocked_apply_helper`,
`continue_residual_unlocked_apply_line`,
`continue_residual_unlocked_apply_ready`,
`continue_residual_unlocked_apply_action`,
`continue_call_residual_focused_validation`, nested
`continue_residual_focused_validation`,
`continue_residual_focused_validation_helper`,
`continue_residual_focused_validation_line`,
`continue_residual_focused_validation_ready`,
`continue_residual_focused_validation_action`,
`continue_call_residual_handoff`, nested `continue_residual_handoff`,
`continue_residual_handoff_helper`, `continue_residual_handoff_line`,
`continue_residual_handoff_ready`, `continue_residual_handoff_action`,
`continue_call_residual_acceptance`, nested `continue_residual_acceptance`,
`continue_residual_acceptance_helper`, `continue_residual_acceptance_line`,
`continue_residual_acceptance_ready`, `continue_residual_acceptance_action`,
nested `continue_residual_cascade`, `continue_residual_cascade_helper`,
`continue_residual_cascade_line`, `continue_residual_cascade_ready`,
`continue_residual_cascade_action`, `continue_residual_cascade_progress_label`,
`continue_residual_cascade_blocked_at`, nested `continue_cascade`,
`continue_cascade_helper`, `continue_cascade_line`, `continue_cascade_ready`,
`continue_cascade_action`, `continue_cascade_reverse_progress_label`,
`continue_cascade_residual_progress_label`,
`continue_cascade_residual_blocked_at`, nested
`continue_cascade_transition`, `continue_cascade_transition_helper`,
`continue_cascade_transition_line`, `continue_cascade_advanced`,
`continue_cascade_reverse_progress_transition`,
`continue_cascade_residual_progress_transition`, nested
`continue_cascade_wake`, `continue_cascade_wake_helper`,
`continue_cascade_wake_line`, `continue_cascade_wake_outcome`, nested
`continue_cascade_wake_route`, `continue_cascade_wake_route_helper`,
`continue_cascade_wake_route_line`, `continue_cascade_wake_route_action`,
`continue_cascade_wake_route_call_execute`, nested
`continue_cascade_wake_route_apply`,
`continue_cascade_wake_route_apply_helper`,
`continue_cascade_wake_route_apply_line`,
`continue_cascade_wake_route_action_transition`,
`continue_cascade_wake_route_advanced`, nested
`continue_cascade_wake_route_apply_follow`,
`continue_cascade_wake_route_apply_follow_helper`,
`continue_cascade_wake_route_apply_follow_line`,
`continue_cascade_wake_route_apply_follow_action`,
`continue_cascade_wake_route_apply_follow_preferred_helper`,
`continue_cascade_wake_route_apply_follow_call_execute`, nested
`continue_cascade_wake_route_apply_follow_pin`,
`continue_cascade_wake_route_apply_follow_pin_helper`,
`continue_cascade_wake_route_apply_follow_pin_line`,
`continue_cascade_wake_route_apply_follow_pin_action`,
`continue_cascade_wake_route_apply_follow_pin_mode`,
`continue_cascade_wake_route_apply_follow_pin_preferred_helper`,
`continue_cascade_wake_route_apply_follow_pin_call_execute`,
`continue_cascade_wake_route_apply_follow_pin_ready`, nested
`continue_cascade_wake_route_apply_follow_pin_call`,
`continue_cascade_wake_route_apply_follow_pin_call_helper`,
`continue_cascade_wake_route_apply_follow_pin_call_line`,
`continue_cascade_wake_route_apply_follow_pin_action_transition`,
`continue_cascade_wake_route_apply_follow_pin_mode_transition`,
`continue_cascade_wake_route_apply_follow_pin_advanced`, nested
`continue_cascade_wake_route_apply_follow_pin_call_next`,
`continue_cascade_wake_route_apply_follow_pin_call_next_helper`,
`continue_cascade_wake_route_apply_follow_pin_call_next_line`,
`continue_cascade_wake_route_apply_follow_pin_call_next_action`,
`continue_cascade_wake_route_apply_follow_pin_call_next_invoke`,
`continue_cascade_wake_route_apply_follow_pin_call_next_preferred_helper`,
`continue_cascade_wake_route_apply_follow_pin_call_next_call_execute`, and
`continue_cascade_wake_route_apply_follow_pin_call_next_ready` while reverse-flow is
ready/unrecorded or after pass. After a
recorded pass,
`skill_route_discovery_focused_validation_activation_external_handoff` packages
`keep_activation_external_after_focused_local_test_validation` into one
operator-visible packet while push, promotion, provider launch, remote apply,
external skill execution, and kernel restart stay denied. Supervisors may close
a ready focused surface with
`close_skill_route_discovery_focused_local_test_validation_with_outcome` (body-free
expected-hash materialization via
`build_skill_route_discovery_focused_validation_body_free_command_results`) without
re-listing commands. When the activation-external handoff is ready after a
recorded pass,
`skill_route_discovery_focused_validation_activation_external_acceptance` accepts
the package (`accept_activation_external_package_after_focused_validation_pass`)
while residual fortress/Hy3 rows stay adjacent harness-eval only and activation
stays external. After acceptance is `accepted` and residual adjacent proposal IDs
remain, `skill_route_discovery_focused_validation_residual_adjacent_queue`
packages those rows for `agent_harness_eval_cluster_local_apply` without skill
unlock inheritance (`queue_residual_adjacent_harness_eval_after_focused_validation_acceptance`).
When that residual queue is `ready`,
`skill_route_discovery_residual_adjacent_harness_eval_local_apply` selects one
residual fortress/Hy3 proposal (prefer fortress) and hands it to
`agent_harness_eval_cluster_local_apply` with local comparison required and skill
unlocks closed
(`hand_off_selected_residual_adjacent_row_to_agent_harness_eval_cluster_local_apply`,
`prop-residual-adjacent-fortress-harness-eval`). When residual local apply is
`ready`,
`skill_route_discovery_residual_adjacent_harness_eval_local_comparison` runs
residual harness local comparison and unlocks only documentation, test, or
code_patch after criteria pass while skill-route unlocks stay closed
(`unlock_documentation_test_or_code_patch_after_residual_adjacent_harness_local_comparison`).
When residual harness comparison is `ready`,
`skill_route_discovery_residual_adjacent_unlocked_local_lane_apply` packages
test-first residual unlocked documentation/test/code_patch apply without skill
unlock inheritance
(`apply_unlocked_documentation_test_or_code_patch_with_focused_validation_and_keep_activation_external`).
When residual unlocked apply is `ready`,
`skill_route_discovery_residual_adjacent_focused_local_validation` records
body-free command-hash results for the residual selected lane while skill unlocks
stay closed and activation remains external
(`run_residual_adjacent_focused_local_validation_with_body_free_command_hashes`,
`prop-residual-adjacent-fortress-harness-eval`). Supervisors close residual focused
results via
`record_skill_route_discovery_residual_adjacent_focused_local_validation_results`
or
`close_skill_route_discovery_residual_adjacent_focused_local_validation_with_outcome`.
When residual focused validation is `passed`,
`skill_route_discovery_residual_adjacent_focused_validation_activation_external_handoff`
packages
`package_activation_external_handoff_after_residual_adjacent_focused_validation_pass`
while remaining residual fortress/Hy3 proposal IDs stay noted without skill unlock
inheritance and activation remains external. When residual activation-external
handoff is `ready`,
`skill_route_discovery_residual_adjacent_focused_validation_activation_external_acceptance`
accepts the residual keep_activation_external package
(`accept_activation_external_package_after_residual_adjacent_focused_validation_pass`)
while remaining residual fortress/Hy3 rows stay noted without skill unlock
inheritance and activation remains external. While residual handoff is still
blocked waiting on earlier reverse-flow stages, residual acceptance inherits the
handoff's cascaded supervisor next action and does not override operator-visible
pipeline next with a spurious residual-handoff repair signal. Render priority
goes further: residual stages that are only reverse-flow-waiting (for example
`blocked_until_activation_external_acceptance` or
`blocked_until_residual_adjacent_focused_validation_ready`) do not own
`supervisor_next` at all, so reverse-flow focused validation stays primary while
ready/unrecorded or failed. Residual selected proposal is not advertised in
pipeline render until residual work is residual-active; residual stage packets
also leave `selected_residual_proposal_id` empty while reverse-flow-waiting
(`residual_selection_held_until_residual_active`). Focused validation packets
mark `residual_adjacent_hold_until_recorded` while unrecorded and
`residual_adjacent_hold_active` while unrecorded or failed.
Use
`pytest tests/test_github_growth.py -q -k skill_route_discovery_unlocked_local_test_lane_apply`
and
`pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation`
and
`pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_local_validation`
and
`pytest tests/test_github_growth.py -q -k skill_route_discovery_residual_adjacent_focused_validation_activation_external`
for the unlocked-lane apply, focused-validation, activation-external handoff,
acceptance, residual-adjacent queue, residual harness-eval local-apply,
residual harness-eval local-comparison, residual unlocked-lane apply, residual
focused-validation, residual activation-external handoff, and residual
activation-external acceptance regressions.
Fortress-style general-agent projects remain adjacent
`agent_harness_eval_required` rows without skill-route inheritance.
When residual fortress-style general-agent proposals are selected after
skill-route reverse-flow work is exhausted, the pipeline emits
`skill_route_discovery_adjacent_harness_eval_handoff` and defers to
`agent_harness_eval_cluster_local_apply` instead of failing skill-route
comparison or requesting reverse-flow repair. The residual-adjacent queue after
focused-validation acceptance is the reverse-flow companion path: it queues
fortress/Hy3 proposal IDs while reverse-flow remains the selected step and
activation stays external. The residual harness-eval local-apply surface then
selects one residual row; residual harness-eval local-comparison unlocks
documentation/test/code_patch after criteria pass; residual unlocked apply and
residual focused validation then package and record the preferred focused local
lane without skill unlock inheritance. After residual focused validation pass,
residual activation-external handoff packages keep_activation_external and may
note remaining residual rows; residual activation-external acceptance then
accepts that package while remaining residual rows stay noted.
Agent-chief-style privacy evidence stays `privacy_boundary_review_only`.
Runtime action stays `none`; external skill execution, provider launch, remote
apply, push or promotion, and kernel restart remain denied. The packet exports
proposal IDs, route profiles, lane names, hashes, and booleans only. Use
`pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline`
for the current regression.

`package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call`
collapses pre/post continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next
into body-free
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call_line`
with pre→post next action/invoke transition (for example
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call
pre_action=execute_now post_action=keep_activation_external
action=execute_now→keep_activation_external
invoke=execute_helper→package_helper call_execute=true→false
next_advanced=true next_ready=true→true residual_route=false→false
reverse=0/3→3/3 residual=0/8→0/8 executed=true recorded=true
residual_export=false
next=keep_activation_external_after_focused_local_test_validation
helper=package_reverse_flow_focused_validation_continue_finish_receipt
pin_call_next_helper=package_reverse_flow_focused_validation_continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next`).
Follow/dispatch/operator_state export nested
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_call_line` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_action_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_invoke_transition` /
`continue_cascade_wake_route_apply_follow_pin_call_next_call_follow_pin_call_next_call_follow_pin_call_next_advanced` so
supervisors pin one deep next-call receipt instead of re-comparing nested deep pin_call_next packets after continue wakes.
Residual export stays denied.

For the `upstream-evidence-capability` theme, digests also emit
`upstream_evidence_capability_step`: one operator-visible local step derived from
the current proposals. The packet classifies each proposal (privacy or offensive
review-only boundaries, weak/untitled PR compare-before-draft routes, ready
local validation candidates, and follow-up-only rows), then selects a single
next capability action. Weak Hy3-style untitled pull request evidence maps to
`compare_pull_request_approach_with_local_agent_behavior_before_draft` rather
than direct code adoption. Agent-chief-style privacy-leakage signals stay
`privacy_boundary_review_only`. The packet exports proposal IDs, route classes,
hashed evidence URLs, gates, and booleans only; raw evidence URLs, upstream
bodies, credentials, and personal data remain omitted. Runtime action stays
`none`; provider launch, external harness execution, remote execution, push or
promotion, and kernel restart remain denied until a supervisor path permits
them.

Pass 2 of the same theme deepens that translation through
`agent_harness_eval_cluster` on `agent_harness_eval_lane`. Broad
`general_agent_project` signals such as agent-chief, Hy3, and fortress are
queued with `evaluation_lane=agent_harness_eval_required` and
`local_validation_required=true`. The cluster documents comparison criteria,
keeps `runtime_action=none`, refuses star-count-only behavior patches, unlocks
only documentation, test, or code_patch after local comparison, and retains
privacy-class rows review-only. Use
`pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster` for the
current regression.

Pass 3 applies one selected local validation candidate through
`agent_harness_eval_cluster_local_apply`. When the capability step is
`apply_one_local_validation_candidate` (for example Hy3), the lane evaluates the
cluster comparison criteria for that one row, unlocks only documentation, test,
or code_patch after the comparison passes, keeps `runtime_action=none`, never
adopts foreign agent behavior from stars, and refuses privacy-class selected
rows such as agent-chief. Use
`pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply`
for the current regression.

Pass 4 completes the slice through
`agent_harness_eval_cluster_local_apply_completion`. Proposal ids such as
`prop-hy3-harness-eval-local-apply` resolve to the matching general-agent cluster
row by project token, local comparison still has to pass before any lane unlock,
and the completion handoff marks `upstream-evidence-capability` complete only
when unlocked lanes are documentation, test, or code_patch with
`runtime_action=none`. The handoff records the capability pipeline, retained
privacy review-only rows, and a supervisor next action for focused local
validation; it does not authorize activation, push, promotion, provider launch,
external harness execution, remote execution, or kernel restart. Use
`pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply_completion`
for the current completion regression.

### Selectable Local CLI Kernel

Runs only when explicitly selected with `--evolution-mode codex`. The `--kernel codex|grok` selector chooses the local execution backend without changing the surrounding rollback and promotion protocol.

The controller creates a coherent task from the digest proposals, writes a rollback point, prepares a local branch, and invokes:

```text
codex exec --cd <repo> --ignore-user-config --sandbox workspace-write --ephemeral -
```

The task is passed through stdin, and Codex writes its final response to an output artifact with `--output-last-message`.
Operators that want the autonomous loop to mutate without the Codex sandbox can pass `--bypass-approvals-and-sandbox`, which forwards Codex's explicit full-access bypass flag.

The Grok route invokes the equivalent headless contract:

```text
grok --cwd <repo> --output-format json --permission-mode bypassPermissions --sandbox workspace --prompt-file <task>
```

Grok tasks are stored in a prompt file so long controller tasks do not enter the process command line. Cross-session memory, subagents, and Grok-hosted web search are disabled for bounded supervisor children; the supervisor remains responsible for commit, health gates, promotion, push, and restart handoff.

The kernel is intentionally local:

- local source mutation is allowed on the prepared evolution branch
- material actions must be written to run artifacts
- remote writes require configured runtime capability
- schedule and restart changes are activated by the native supervisor or another configured runtime supervisor

### Rollback Gate

Before any self-evolution branch is prepared, the controller records:

- original branch
- original HEAD
- local rollback ref
- pre-run dirty status
- explicit recovery commands

The rollback point is written to `latest-rollback-point.json` and `latest-rollback-point.md` in the run output directory. It is the universal recovery path if a future activation fails to start or behaves unsafely.

Rollback execution is intentionally explicit because it uses destructive commands such as `git reset --hard` and `git clean -fd`. A human operator or external supervisor policy must choose it.

### Verification Gate

Runs local checks for any generated patch or config change. A failed verification produces a digest entry and stops the write path.

Local agent-harness comparison reports use a body-free adapter: prompt, output, stdout, and stderr bodies are omitted from exported summaries, and ordinary comparable bodies are represented only by stable hashes. If a fixture declares `privacy-leakage-human-review` or an equivalent privacy flag, the adapter records a review-only outcome and omits body hashes too. That keeps privacy-leakage validation cases useful for local regression tests without turning sensitive task content into report material.

The same module also provides a small local eval adapter for deterministic JSON fixtures. Each fixture names a supported behavior such as `harness_run_summary` or `proposal_interpretation`, supplies an input object, and declares exact field assertions. The resulting report is controller-readable, includes pass/fail counts plus assertion failures, and exports only a stable input hash rather than the raw task or output body. This keeps offline harness lessons reproducible without requiring network access, model credentials, or remote execution.

`agent_workflow_route` fixtures model controller-visible one-shot agent runs. When a fixture declares `oneshot_marker.required`, the evaluator checks marker presence before activation and reports `blocked_before_activation` with `oneshot_marker_missing` if the marker is absent. Marker paths are hashed rather than exported, and the evaluator does not launch or restart the runner. This gives harness evidence about absent one-shot markers a deterministic local pass/fail lane while preserving explicit supervisor control over restart and recovery.

The same route can declare `orchestrator_inbox.required` for sub-agent delivery replay. The evaluator requires exactly one completion message by default, a parent wake, non-empty child output, no transcript-only completion recovery, and non-degraded child lifecycle metadata such as present sub-agent identity, stable send handle, and close support. Message IDs, child session IDs, turn IDs, transcript bodies, and payload bodies are hashed or omitted. Missing delivery, duplicate delivery, empty turns, transcript-only completion, parent wake failure, and degraded lifecycle are distinct local failure modes. The contract also reports whether transcript polling is available only as recovery, whether child-session cleanup is required or blocked, and the operator action to replay or recover the route, so runner-control regressions can be reviewed without busy-polling a live child session as normal behavior.

The same route can carry idle-watchdog diagnostics. When a runner times out after a recent transport error, the evaluator reports the watchdog timing and a normalized root-cause class such as `no_route_to_host` instead of collapsing the run to a generic timeout. Raw request bodies, error bodies, URLs, headers, and event ids are omitted or hashed, so connectivity root-cause replay remains operator-visible without exporting sensitive session or request data.

Harness-owned compaction is part of the same route contract. A required compaction event must be owned by the harness, completed, summarized, token-counted, persisted, checked after persistence, mirrored only after persistence, and replay-ready while runner-side compaction remains disabled. The compaction record must also preserve controller metadata for source digest, branch, HEAD, rollback ref, and recovery commands; reports export only counts and stable hashes for that metadata, never raw refs, commands, summaries, or context bodies. A missing metadata packet blocks as `compaction_controller_metadata_missing`.

The same route now emits a `runner_harness_control_plane` summary that ties intake, mid-flight state, recovery, replay, and report artifacts into one operator-visible contract. Replay and report paths are represented only by hashes. The nested `workflow_handoff` packet orders those five stages, verifies the canonical intake -> midflight -> recovery -> replay -> report order, records ready and blocked counts, summarizes source intake, mid-flight state, recovery, replay, and report artifacts, and repeats blocked-stage reasons without exporting raw URLs, commands, report bodies, or paths. Its artifact manifest labels the stage artifact kind (`source_digest_and_evidence`, `state_transition_trace`, `rollback_and_operator_recovery`, `local_replay_fixture`, or `operator_report`) with ready/recorded booleans, counts, and hash-presence flags so an operator can inspect the full runner workflow without raw paths or command bodies. Fixtures can require an explicit recovery handoff with operator-reset commands and a replay command; the evaluator exports only command counts and hashes, and marks the recovery stage missing when a required handoff is incomplete. Fixtures can also declare observations as load-bearing or non-load-bearing; unreliable observations are allowed only when marked non-load-bearing, so flaky teardown/status probes can be recorded without becoming silent pass/fail gates. A load-bearing unreliable observation fails locally as `unreliable_load_bearing_observation`.

For pull-request-driven e2e migration work, the same intake contract can include `pull_request_events` plus a `controller_recomputed` block. A passing local checklist requires PR fixture events to record event kind, repository or source URL, proposal IDs, requested scope, and requested validation gate; duplicate PR events must be collapsed; generic or untitled PR titles must be counted and excluded from final scope; and controller-recomputed proposal IDs, final scope, and validation gates must match the remaining unique, specific PR events. The report exports only hashes, counts, booleans, and blocker codes, not raw PR titles or URLs. Use `pytest tests/test_harness_eval.py -q -k agent_workflow_route_pr_migration_intake` when upstream evidence proposes PR migration, generic PR handling, deduplication, or final-scope gate recomputation changes.

`agent_harness_provider_registration` fixtures validate proposed provider harness registrations before activation. A Qwencode-style provider can be represented as metadata with required commands and environment keys, then blocked as `required_provider_config_missing` when the local command or config is absent. The lane does not launch the provider, import an SDK, install packages, or expose environment values; env-key identifiers are represented by hashes in diagnostics. Use `pytest tests/test_harness_eval.py -q -k agent_harness_provider_registration` when current-wake harness evidence proposes a new provider registration path.

For skill-route discovery pass 2, the route map also emits `skill_route_discovery_pass2_retained_validation_packet`. This packet turns selected skill-route candidates into phase-gated retained validation metadata before activation: evidence intake, skill-route phase gate, retained validation replay, adjacent agent-harness queue, and activation boundary. Replay commands are represented only as hashes, adjacent general-agent projects remain behind `agent_harness_eval_required`, and external skill activation, provider launch, remote execution, raw URLs, raw commands, and upstream bodies stay disabled.

The skill-route evaluator also exposes `pass2_route_probe` for active pass-2 windows that mix a skill/workflow repository with adjacent general-agent project trends. The probe is an operator-visible aggregate: skill/workflow rows must stay in `skill_route_discovery_first` with only documentation, config, test, or code-patch lanes, while adjacent general-agent rows must declare the local agent-harness probe fields before they can be replayed through `agent_harness_eval_lane`. A ready probe still performs no install, clone, runtime execution, provider launch, remote execution, or upstream body export; it only names the local replay commands and the next supervisor action. The nested `operator_activation_checkpoint` orders the supervisor handoff as controller recomputation, bounded skill-route replay, then adjacent agent-harness replay. It is still metadata-only: activation remains a candidate after the checkpoint, general-agent rows keep no direct pre-eval lanes, and all external skill, agent, harness, provider, and remote execution routes remain disabled.

The proposal route map exposes the same ordering as `current_pass2_activation_checkpoint` so scheduled growth passes can inspect the checkpoint before any harness fixture is added. The checkpoint records skill rows as replay-ready only when their selected lane is one of documentation, config, test, or code_patch, records generic skill collections such as `rnskill` as skill-route discovery rather than installable packages, and keeps Shepherd-style runtime substrates in `agent_harness_eval_required`. Replay commands, source URLs, evidence URLs, target paths, and upstream bodies remain omitted or hashed.

`agent_harness_policy_eval` fixtures validate a proposed local harness action plan before any action can run. Each action must have a policy decision with an earlier sequence index; missing policy, late policy, unknown outcomes, ASK/DENY/review outcomes, external harness execution, provider launch, remote execution, credential access, or upstream agent activation all block as pre-execution failures. Reports keep action ids and policy ids hashed, omit raw commands, policy bodies, credentials, and provider config, and mark `execution_attempted: false`. Use `pytest tests/test_harness_eval.py -q -k agent_harness_policy_eval` when upstream agent-harness evidence proposes executable capability registration or validation.

`agent_harness_eval_lane` also emits a body-free `agent_harness_fork_cluster_eval_queue` when repeated forks point at the same upstream general-agent project. The queue collapses fork events into one `agent_harness_eval_required` candidate, preserves each `item_id` for traceability, hashes source and upstream URLs, and keeps direct runtime, direct code patch, external harness execution, provider launch, and remote execution disabled until local validation passes. Use `pytest tests/test_harness_eval.py -q -k "agents_a1_fork_cluster or agent_harness_eval_lane"` for the current Agents-A1-style fork-cluster regression.

General-agent activity intake also emits `project_activity_groups`. This groups repeated trend, push, issue, and pull-request activity by hashed upstream project before route interpretation. Low-detail pushes and untitled pull requests count as freshness signals, not independent implementation pressure, so several events from the same upstream project remain one `agent_harness_eval_required` candidate. Raw source URLs and activity bodies are not exported. Use `pytest tests/test_harness_eval.py -q -k "low_detail_activity or agent_harness_eval_lane"` when current public activity should influence harness-eval priority without directly enabling code, config, provider, or runtime changes.

Pass-3 skill-route handoffs expose `skill_route_discovery_pass3_supervisor_activation_gate`. It aggregates the selected replay queue, proposal-lane contract, local validation probe, promotion runbook, runner control plane, and adjacent general-agent holdback into one body-free supervisor decision. Replay commands are represented by hashes, adjacent general-agent projects remain gated to `agent_harness_eval_required`, and activation, push, restart, provider launch, remote execution, raw URLs, raw commands, and upstream bodies remain denied. Use `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_pass3"` when a current skill-route window needs one operator-visible pass-3 replay gate before pass 4.

The same lane can replay host-registration state before provider activation. If a fixture shows that a host id is already registered to one owner but the current authenticated owner differs, or if a controller would report connection success before registration completes, the lane blocks as `host_registration_owner_mismatch` or `host_registration_incomplete_success_state`. Host ids and owner values are hashed only, provider launch remains false, and the recovery hint tells the operator to refuse the connected state until stale registration or host-id reset is handled.

`mock_llm_workflow_route` fixtures are expected to prove that the mock provider path was actually exercised. The evaluator records whether every queued mock response was consumed, and when file tools or native policy hooks are declared it checks that consumed mock turns included the required tool-call names. OpenAI-compatible mock server lanes can also declare a `/v1/chat/completions` contract: non-streaming requests must receive JSON-shaped mock responses, streaming requests must receive SSE-shaped mock responses, consumed request counts must match the workflow, and mock auth/base-url preflight failures are classified separately from mock-server contract drift. Raw tool arguments, chat messages, responses, base URLs, and token values are not exported; tool-call names used for the contract are reported by count and hash. A route that leaves responses queued, never observes a declared tool boundary, returns the wrong mock response format, or fails provider preflight fails locally instead of passing from absence of side effects alone.

`headless_tool_roundtrip` fixtures cover the narrower headless dispatch path where a model stream emits `function_call` or `tool_call` events. The local report normalizes those events, routes them through the same executable descriptor and policy checks used by the tool registry, and records whether each function call was dispatched, blocked, or missing a handler. It is intentionally dry-run only: raw event bodies and arguments are omitted or hashed, and tool callables are never executed by the harness.

`mock_e2e_runner_tier` fixtures can require an approval boundary for host-native journeys. When `approval_boundary.required` is set, the evaluator reuses the native policy-hook adapter and only passes if the mocked journey preserves an ASK/review path on the controller surface without executing the tool call. Raw commands, policy payloads, session IDs, paths, and content remain omitted or hashed.

`known_failure_metadata_preflight` fixtures run before a growth pass treats test evidence as current. The preflight compares expected and current known-failure metadata, detects absent metadata, empty current metadata, removed entries, unexplained changes, and missing gate-refresh records, then reports `test_gating_should_refresh` plus body-free recovery hints. Failure IDs are represented only as hashes, raw test names and failure text are not exported, and the lane does not edit quarantine files or execute tests. Use `pytest tests/test_harness_eval.py -q -k known_failure_metadata_preflight` when upstream push or PR activity suggests known-failure metadata was removed, repointed, or stale.

The same mock E2E lane can carry a compact single-file agent YAML document as `agent_config.yaml`. This validates YAML parsing and controller tool routing with the local single-file agent parser, but it does not execute the declared agent, import the callable, contact a provider, or require credentials. Reports include only YAML hashes, route counts, executable-tool counts, required-tool diagnostics, and hashed tool names; raw prompts, callable paths, commands, fixture paths, and YAML bodies stay out of controller output. A configured YAML route fails locally when parsing fails, no function tools are declared, required tools are missing, or parsed tools cannot reach the executable local registry.

`push_delivery_path` fixtures model the final promotion delivery handoff without performing a remote write. They require a successful promotion target, an explicitly requested push, a mocked runner command shaped like `git push <remote> <branch>`, activation and restart-request records, and rollback metadata. The evaluator fails if the route would require credentials, network, or an unmocked remote call, and it exports only booleans and hashes rather than raw remotes, branches, commands, or credential material. This gives upstream push/test activity a local regression lane while keeping actual push activation under supervisor runtime policy.

`proposal_interpretation` fixtures adapt small agent task cases into the frozen proposal interpreter. Their JSON output records review status, selected item IDs, accepted proposal IDs, validation preflight metadata, evidence-ref policy, and a compact safety-boundary summary without exporting the raw digest or model response. Accepted `evidence_refs` are checked against the supplied digest `item_id` values and the selected context item IDs, so URL citations or invented references remain rejected by local regression cases. The safety summary is metadata only: proposals flagged for offensive behavior or privacy leakage must remain `reviewable_proposal_only` behind a human-review gate, and the local adapter does not execute offensive benchmark behavior.

`provider_runtime_preflight` fixtures model provider startup without live SDK calls. They treat browser tooling such as Playwright as optional: missing browser configure support produces a degraded/skipped diagnostic, but URL safety is evaluated independently and can still block launch. Native terminal launch risks are also modeled before long sessions start: a macOS iTerm2/tmux Claude Code route whose native CLI is not visible to the runner is blocked as `native_terminal_timeout_risk`. Provider setup readiness can be checked with a metadata-only `setup_preflight` block before installers or adapter activation run: unwritable or non-user-owned global npm prefixes block as `provider_setup_npm_prefix_unwritable`, LiteLLM adapter model IDs without required provider prefixes block as `provider_setup_litellm_model_prefix_missing`, and required LiteLLM model discovery with no discovered models blocks as `provider_setup_litellm_model_discovery_missing`. Setup paths, package names, install commands, URL-like adapter inputs, and model IDs are hashed or counted rather than exported. Provider harness startup can be checked with a metadata-only `startup_preflight` block: executable resolution, platform support, provider config presence, and Errno 8-compatible exec-format failures are classified before launch as `provider_startup_*` recovery classes, while executable paths, config values, stderr, and raw error bodies are omitted or hashed. Windows-native runner startup can be checked with a metadata-only `windows_runner` block: unsupported shell families, shell-body command strings, unquoted path arguments, unresolved or out-of-repo workspaces, and missing local replay proof block as `provider_windows_runner_*` classes before launch. When Windows-native support explicitly allows degraded mode, unavailable shell, dependency, or capability metadata can instead produce `provider_windows_runner_degraded_mode`, keep `local_replay_only: true`, and keep provider runtime launch denied until the missing support is repaired; without that allowance, dependency or capability gaps block as `provider_windows_runner_capability_unavailable`. Command arguments, path values, workspace values, dependency names, capability names, and shell bodies are hashed, counted, or omitted. Kubernetes managed-sandbox provider metadata can be checked with a body-free `kubernetes_sandbox` block before any cluster access: missing namespace, image, or service-account metadata blocks as `provider_kubernetes_sandbox_config_missing`; malformed DNS-label names, argv-unsafe image metadata, or malformed node selectors block as `provider_kubernetes_sandbox_config_malformed`; credential-looking env keys block as `provider_kubernetes_sandbox_credential_env_inline`; token-dependent options without server-minted launch-token metadata block as `provider_kubernetes_sandbox_launch_token_missing`; and inline launch-token values block as `provider_kubernetes_sandbox_token_value_configured`. Raw namespaces, images, service accounts, secret names, selectors, env key names, token values, provider config bodies, and cluster responses are omitted; the preflight records booleans, counts, failure classes, and `cluster_access_attempted: false`. Claude-native prompt readiness can be checked with a metadata-only `prompt_scan` block: fixtures record scan-tail limits, status-footer line counts, prompt distance, timeout seconds, whether legacy tail scanning would miss the prompt, and whether a second message would time out. Pane text is not exported. Review-model configuration can be checked with a metadata-only `review_models` block before review execution; unavailable, unsupported, missing, or required-but-unexercised model routes block as `review_model_*` failure classes. Provider wire API routing can be checked with a metadata-only `wire_api` block: `chat`, `responses`, and `completions` aliases are normalized, unsupported routes block as `provider_wire_api_unsupported`, missing required routes block as `provider_wire_api_missing`, and `wire_api: chat` must be exercised by local route evidence or it blocks as `provider_wire_api_unexercised`. Header-auth routing can be checked with a metadata-only `auth_header` block: missing required headers block as `provider_auth_header_missing`, invalid HTTP field names block as `provider_auth_header_malformed`, and a custom trusted identity header that leaves the default header accepted blocks as `provider_auth_header_fallback_ambiguous`. Auth precedence routing can be checked with a metadata-only `auth_precedence` block: when a Claude or Codex harness declares LiteLLM/Bedrock/proxy auth as the expected route and native provider auth fallback is disallowed, missing proxy auth propagation blocks as `provider_auth_precedence_fallback_risk` before launch. The preflight records route labels, key counts, key hashes, and missing counts only; environment key names, token values, proxy URLs, and secrets are not exported. Approval re-park routing can be checked with a metadata-only `approval_repark` block: if fresh provider state still lists the same elicitation as pending after a local optimistic approval/denial verdict, the stale verdict is reported as cleared and launch blocks as `provider_approval_repark_pending` until the pending approval is replayed explicitly. Header names, header values, approval ids, approval verdicts, snapshots, and header env names are not exported; reports keep presence booleans, counts, hashes, and recovery classes. Provider throttling can be replayed with a metadata-only `usage_limit` block: status 429 or exhausted `anthropic-ratelimit-unified-*` windows block as `provider_usage_limit_exhausted`, while response bodies, raw header values, reset strings, retry-after values, credential labels, and credential material are omitted or hashed. Credential-pool failover remains review-only in this lane because labels and tokens are privacy-sensitive; the preflight records that failover was not executed. This is intended for CI/review provider changes where setup installation would fail due to local permissions, opaque model identifiers may be renamed, unsupported by the configured gateway, temporarily unavailable due to provider limits, wired to the wrong chat/responses route, configured with an ambiguous trusted identity header, missing LiteLLM/Bedrock auth environment propagation, or re-parked with stale local approval state. Raw review bodies, raw model IDs, raw provider wire API values, raw auth header names, raw auth header values, raw approval ids, raw approval verdicts, raw approval snapshots, auth header env names, auth precedence env key names, and auth precedence env values are omitted; reports keep provider labels, normalized route enums, counts, hashes, and recovery classes. Worker-scoped env inheritance is capability-aware: if a fixture explicitly targets a `*_worker` tool and the harness declares no worker tool, the env-inherit invariant is reported as skipped instead of blocking or forcing os-env propagation. A long Claude Code status footer above a prompt should be validated with `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`, and a too-small scan window should fail as `prompt_scan_timeout_risk` before a live provider session is launched. Base URL values, CLI paths, pane text, review text, provider response bodies, rate-limit reset values, credential labels, wire API raw values, auth header raw values, auth precedence raw values, approval verdicts, approval snapshots, setup paths, setup commands, npm package names, Windows runner commands, Windows path arguments, Windows workspaces, Windows dependency names, Windows capability names, Kubernetes namespaces, Kubernetes images, Kubernetes service accounts, Kubernetes secrets, Kubernetes selectors, Kubernetes env names, Kubernetes token values, and environment values are recorded only as presence booleans, normalized integration labels, counts, hashes, and failure classes, not as raw URLs, paths, prompts, review bodies, provider bodies, credential identifiers, provider config bodies, approval bodies, commands, packages, model IDs, Kubernetes config bodies, or secrets.

Runner-generated wire API metadata is part of the provider preflight contract. A configured `wire_api: chat` route may be supplied at the top level or inside nested OpenAI-compatible provider config shapes such as `openai.wire_api` or `provider_config.openai.wire_api`; the preflight resolves these shapes without exporting raw provider config bodies. A configured chat route must not silently resolve to a runner `responses` route; that blocks as `provider_wire_api_runner_mismatch`. Pi-style `openai-completions` labels are normalized to the local chat-completions route. Raw runner labels are not exported.

Provider tool-dispatch metadata is also checked before launch. If a non-OpenAI model route enables the `web_search` builtin, the preflight requires either a registered local runner dispatch handler or local dispatch replay evidence; otherwise it blocks as `provider_tool_dispatch_missing`. OpenAI native web-search passthrough remains allowed without a local handler. Tool names are represented by counts and hashes, and raw tool config bodies, arguments, provider responses, URLs, and credentials are not exported.

Provider model inventory source attribution is checked before launch as
metadata only. Fixtures can supply `model_inventory` rows for
`sys_list_models`-style output, including cursor-native worker rows. A
dispatchable row whose source resolves to `none`, `unknown`, or an empty value
blocks as `provider_model_source_none`; a required but absent inventory blocks
as `provider_model_inventory_missing`. Worker labels, source labels, and model
identifiers are hashed or counted only, so the check catches misleading
inventory rows without exporting raw provider config or model ids.

Old runner/host to current server compatibility is also modeled inside
`provider_runtime_preflight`. A fixture can declare `runner_compat` for the
Config-2-style bridge where the runner and host are pinned as one colocated old
component while the server stays current. The preflight blocks launch until the
compat runner python and version backstop are configured, runner/host colocation
is preserved, worktree `PYTHONPATH` is dropped, a neutral cwd is used, and local
resolution proof has been replayed. Failures use stable classes such as
`provider_runner_compat_bridge_missing`,
`provider_runner_compat_env_not_neutralized`,
`provider_runner_compat_colocation_mismatch`, and
`provider_runner_compat_replay_missing`. Interpreter paths, version strings,
cwd, environment values, and raw config bodies are not exported; reports keep
booleans, counts, normalized direction labels, replay commands, and recovery
hints.

`provider_runtime_recovery_summary` fixtures aggregate multiple provider-runtime preflight cases into an operator-visible recovery surface. The summary reports pass/degraded/blocked counts, blocked failure classes, runner-invocation counts, and stable recovery hint codes such as `provider_env_missing`, `native_terminal_timeout_risk`, `prompt_scan_timeout_risk`, `provider_usage_limit_exhausted`, `provider_wire_api_unexercised`, `provider_approval_repark_pending`, `review_model_unavailable`, `url_safety_preflight_failed`, `mock_auth_placeholder_used`, and `browser_configure_checks_skipped`. It also emits `supervisor_readiness`, a body-free handoff decision with replay commands, recovery hint codes, blocked failure classes, and explicit denial of provider runtime launch or remote execution. Usage-limit recovery tells the operator to wait for reset or route credential-pool failover through privacy review; it does not select, rank, print, or switch pooled credentials. When a configured credential pool is present, the usage-limit preflight also emits a `failover_review_plan` with safe next-action codes and local replay commands, while continuing to omit credential labels, token values, raw headers, reset values, and provider response bodies. A degraded-only summary can be ready for local replay, but it is no longer reported as supervisor promotion success: `success_status` sets `provider_runtime_degraded_replay_only`, keeps `success_claim_allowed: false`, and requires operator action while preserving `ready_for_supervisor_local_replay: true`. Blocked preflights remain blocked before supervisor promotion. It does not launch providers and does not export raw preflight inputs, diagnostics, URLs, paths, model IDs, review bodies, provider response bodies, wire API raw values, rate-limit reset values, credential labels, environment values, or environment key names. This lane is intended for locally replayable validation of mock/provider migration work where a scheduler needs the next safe local fix without inspecting provider bodies.

Provider terminal-turn outcomes can also be replayed through `provider_runtime_preflight`. A synthetic completed turn with empty assistant output plus auth/error metadata blocks as `provider_turn_auth_failed`, `provider_turn_error_item_reported`, or `provider_turn_empty_success_suspect` before the runner can treat the turn as successful. The diagnostic exports only terminal-event status, counts, status class, guardrail booleans, and recovery hint codes; raw provider error bodies, assistant output, credential values, token labels, and private turn content are omitted.

When a skill-route validation window includes sampled provider/runtime preflights, the skill-route output carries a projected `skill_route_provider_runtime_recovery_plan`. The projection preserves only decisions, next-action labels, pass/degraded/blocked counts, recovery hint codes and hashes, replay commands, and launch-denial flags. It omits raw provider inputs and diagnostics while making blocked provider/runtime recovery visible from the skill-route diagnostic panel.

`rendered_html_artifact_validation` fixtures validate browser-observable HTML artifacts without exporting HTML bodies, raw URLs, snapshot paths, or image bodies. The lane checks script execution, external-link navigation, and optional UI snapshot gates. Empty landing-state snapshot gates require both baseline and current snapshot hashes plus an observed empty-state marker; missing baselines, missing current snapshots, unobserved empty states, and unapproved diffs are distinct failure modes. This turns upstream UI diff snapshot-gate signals into a replayable local validation path rather than a live browser dependency.

`skill_route_discovery_lane` fixtures replay frozen skill-route evidence through the local discovery registry and proposal lane map before activation. They verify that external skill repositories produce only documentation, config, test, or code_patch lanes; every lane keeps `runtime_action: none`; local validation remains required; and raw source/evidence URLs are hashed rather than exported. The lane also emits a body-free source-lineage summary with candidate source counts, hashed candidate and related source URLs, duplicate summary counts, evidence item ID counts, and fork/mirror collapse status so supervisors can see lineage pressure without treating upstream repositories as installable packages. Actionful discovery requests such as install, enable, run, execute, clone-and-run, or local deletion are reported as rejected candidates and no external skill code is executed.

The same lane emits `skill_route_discovery_route_family_eval_matrix` for mixed evidence windows that contain both skill/workflow candidates and adjacent general-agent projects. Skill rows keep the `skill_route_discovery_first` gate and are limited to documentation, config, test, or code_patch lanes. General-agent rows keep `agent_harness_eval_required`, inherit no skill-route lane, have no direct implementation lanes before evaluation, and may only proceed to documentation, test, or code_patch after local agent-harness validation. The companion `skill_route_discovery_route_family_agent_harness_intake` surface converts those adjacent general-agent rows into a body-free intake queue for `agent_harness_eval_lane`: it lists required probe fields, selected follow-up lanes after evaluation, source hashes, and missing local project-shape fields while denying runtime action, external harness execution, provider launch, remote execution, raw source URLs, and upstream bodies. Use `pytest tests/test_harness_eval.py -q -k "skill_route_discovery_current_digest_20260706T141555_pass3_agent_harness_intake or skill_route_discovery_20260706_pass1_route_family_eval_matrix or skill_route_discovery_lane or agent_harness_eval_lane"` for the current reverse-flow plus Agents-A1/Qwen-AgentWorld/Fundamental-Ava/Shepherd regression.
`agent_harness_eval_lane` also emits `general_agent_project_route_plan` after project-shape probe fields are present. This plan is the ready-state companion to the intake queue: it classifies broad public agent projects as `general_agent_project`, selects `agent_harness_eval_required` before behavior adoption, keeps direct pre-eval lanes empty, and limits post-eval follow-up to documentation, test, or code_patch. Use `pytest tests/test_harness_eval.py -q -k "agent_harness_eval_lane or current_window_general_agent_projects"` for the current ready-state route-plan regression.

The same lane emits `agent_harness_eval_cluster` for mixed general-agent project windows (for example agent-chief, Hy3, and fortress). The cluster is the operator-visible comparison surface for `prop-agent-harness-eval-cluster`: every non-boundary row records `evaluation_lane=agent_harness_eval_required`, `local_validation_required=true`, and `local_comparison_required=true`; `runtime_action` stays `none`; star count alone never unlocks a behavior patch; documentation, test, or code_patch are candidates only after local comparison; privacy-leakage rows remain review-only with hashed source refs and no raw URL export. Use `pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster` for the current cluster regression.

The same lane also emits `agent_harness_eval_cluster_local_apply` when a selected local validation candidate is present or when the cluster has eval-ready rows. That surface evaluates the comparison criteria for exactly one selected general-agent project, unlocks only documentation, test, or code_patch after the comparison passes, keeps `runtime_action=none`, denies foreign agent behavior adoption and star-count behavior patches, and blocks privacy-leakage or offensive selected rows as review-only. Use `pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply` for the current local-apply regression.

The same lane also emits `agent_harness_eval_cluster_local_apply_completion` after local apply. Pass 4 of `upstream-evidence-capability` uses that handoff to select Hy3 via `prop-hy3-harness-eval-local-apply`, complete the theme only when comparison unlocks documentation/test/code_patch, retain agent-chief privacy rows as review-only, and leave supervisor activation, push, promotion, and restart denied. Use `pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply_completion` for the current completion regression.

The pass-4 skill-route completion handoff for `github-growth-20260707T170109.447884Z` adds a route-hint policy regression packet. Reverse-flow skill repositories and `rnskill` stay in `skill_route_discovery` with only documentation, config, test, or code_patch lanes; Shepherd and Agents-A1 activity stay in `agent_harness_eval_required` with no direct lanes before local harness evaluation and only documentation, test, or code_patch after evaluation. Route hints remain metadata and never grant permissions, runtime action, external skill activation, external harness execution, provider launch, remote execution, promotion, or restart authority. Use `python -m pytest tests/test_skill_routing.py -q -k 20260707T170109` for the current completion-lane regression.

The pass-1 focused review lane for `github-growth-20260707T184110.074943Z` replays the active skill-route discovery window directly through `skill_route_discovery_validation_route_packet`. Reverse-flow is selected for a local test lane, `rnskill` is selected for a documentation lane, and Shepherd, Agents-A1, and Fundamental-Ava are queued as `agent_harness_eval_required` before any follow-up implementation lane. The surface exports proposal IDs, item IDs, route profiles, source hashes, and command hashes only; raw repository URLs, upstream bodies, replay commands, install, runtime execution, provider launch, remote execution, promotion, and restart authority remain disabled. Use `python -m pytest tests/test_skill_routing.py -q -k 20260707T184110` for the current focused-review regression.

The pass-4 completion handoff for `github-growth-20260707T210110.348256Z` turns skill/workflow route evidence into bounded local lanes before any activation path. Repositories with `skill_route_discovery` hints, such as reverse-flow skill and `rnskill`, may map only to documentation, config, test, or code_patch, with runtime action set to none and external skill activation disabled. Proposal evidence refs in this lane must cite selected digest `item_id` values only; raw evidence URLs, invented refs, upstream bodies, replay commands, install, runtime execution, provider launch, remote execution, promotion, and restart authority remain disabled. General-agent projects in the same window, such as Agents-A1 and Fundamental-Ava, are queued as `agent_harness_eval_required` with no direct local lanes before local harness evaluation and only documentation, test, or code_patch after evaluation. Use `python -m pytest tests/test_skill_routing.py -q -k 20260707T210110` for the completion-lane regression.

For `github-growth-20260708T044637.626170Z`, the route probe separates `codex_workflow_gate` from generic skill workflow discovery before activation. Reverse-flow-style repositories carry both `codex_workflow_gate` and `generic_skill_workflow` profiles and may open only documentation, config, test, or code_patch local lanes after focused validation; generic SKILL.md collections such as `rnskill` remain documentation-first skill-route evidence. Runtime substrates and workflow-usecase collections, including Shepherd and Blender/Seedance workflow collections, stay in `agent_harness_eval_required` with no direct lanes before local harness evaluation. Use `python -m pytest tests/test_skill_routing.py -q -k 20260708T044637` and `python -m pytest tests/test_harness_eval.py -q -k 20260708T044637` for the current pass-3 route probe.

The implementation readiness contract now includes `promotion_gate`, a compact pass/fail pointer for general-agent trend candidates. The gate reports whether promotion is allowed, links to the contract pass criteria, fail criteria, and per-project completion rows, and keeps direct behavior adoption, pre-eval implementation patches, runtime action, external harness execution, provider launch, remote execution, raw source URLs, and upstream bodies disabled. This gives current windows such as Agents-A1, Fundamental-Ava, Shepherd, and workflow-usecase evidence an operator-visible promotion decision before any documentation, test, or code_patch follow-up is activated.

For pass-2 skill-route windows, the same lane emits `local_lane_acceptance_contract` inside `pass2_handoff_packet`. The contract turns selected and queued route evidence into per-lane acceptance gates for bounded lane membership, local validation, no runtime action, denied external skill/harness/provider/remote execution, and omitted raw upstream evidence. This gives supervisors a direct replay contract for COMPASS-style state handoff, game/frontend skill bundles, and mixed Codex/workflow/skill evidence without treating upstream repositories as installable or executable.

Pass-2 handoff packets also include `secondary_harness_checklist` when the same evidence window contains adjacent general-agent projects such as Qwen-AgentWorld-style benchmark/simulator claims or Fundamental-Ava-style autonomous-agent claims. The checklist records a required `agent_harness_eval_lane` fixture shape: runnable scenario, expected output, pass/fail signal, rollback artifact, and non-secret configuration. Until those local fixture fields exist, adjacent agent rows are blocked as `blocked_until_local_agent_harness_fixture`; they do not inherit skill-route lanes, launch upstream harnesses, start providers, perform remote execution, or export raw source URLs or upstream bodies.

The checklist now exposes `fixture_acceptance_summary`, and `pass2_handoff_packet` mirrors it as `secondary_harness_fixture_acceptance_summary`. This aggregate counts ready versus blocked adjacent general-agent fixtures and per-field declaration coverage without exporting fixture paths, commands, source URLs, or upstream bodies. A ready summary only means the acceptance gate is inspectable; implementation patches, local eval activation, runtime action, external harness execution, provider launch, and remote execution remain disabled until the agent-harness lane passes.

For pass-3 skill-route windows, `pass3_handoff_packet.route_profile_lane_contract` converts each accepted route profile into one bounded local lane before the final pass. Generic skill workflow, game frontend workflow, and skill ecosystem state-handoff profiles can map only to documentation, config, test, or code_patch lanes; each row requires local validation, denies runtime action, external skill or harness execution, provider launch, and remote execution, and exports selected item ids plus source hashes rather than raw upstream URLs or bodies. The pass-3 route index also emits `route_confidence_report`, a body-free local readiness summary that marks complete rows as `bounded_local_ready` and incomplete rows as `needs_local_corroboration` before final-pass replay. It exports counts, profile names, item IDs, and blocker codes only; raw source URLs, raw evidence URLs, target paths, replay-command bodies, upstream bodies, install, external activation, provider launch, and remote execution remain denied.

The current pass-3 replay lane also emits `proposal_replay_plan`, a body-free activation checklist keyed by proposal id. Skill-route proposals get one selected local lane plus validation-task labels such as Codex workflow-gate first or repository-to-lane classification; adjacent general-agent proposals, including AgentWorld-style benchmark projects, remain blocked with `agent_harness_eval_required` until a local harness result exists. The plan exports item ids, lane names, task labels, and counts only; raw upstream URLs, raw evidence URLs, command bodies, upstream bodies, external execution, provider launch, and remote execution remain denied.

When skill-route evidence is blocked or degraded, the same lane emits
body-free diagnostics and recovery hints. Sparse generic PR/push movement, lane
downgrades, rejected candidates, and failed preactivation trust checks are
translated into stable hint codes plus safe local actions and replay commands.
The hints carry counts, booleans, and validation command names only; they do not
export repository URLs, evidence bodies, upstream skill contents, provider
responses, token values, or private paths.

Codex mutation uses a separate provider/config preflight before `codex exec` starts. Controller and supervisor Codex mode require an explicit `--model` or `--profile` by default, write `latest-codex-provider-preflight.json`, and include the route selector in run manifests. This prevents an unpinned agent head from silently falling through to an unintended CLI default provider; `--allow-default-codex-route` keeps the old implicit route available when an operator chooses it deliberately. The same artifact includes metadata-only ambient provider discovery: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, and `GOOGLE_APPLICATION_CREDENTIALS` are recorded as presence booleans, usability booleans, env-name lists, endpoint/source hints, and incomplete-credential diagnostics, never as raw token, URL, or credential-path values. Dummy or placeholder API-key values are treated as invalid credentials before runner launch, and required supervisor token env values distinguish `absent`, `placeholder`, and `provided` without recording the value body. Failed provider/runtime preflights also emit `recovery_hints`: stable failure codes, scopes, safe action text, and environment-variable names only. The top-level supervisor startup preflight aggregates provider, Claude SDK permission, and required-tool recovery hints so a scheduler can display the next local fix without reading nested artifacts or exposing token, URL, profile, or credential-path bodies.

Supervisor startup preflight also records the effective Claude SDK permission mode without importing or launching the SDK. The default is `auto`, unless `--claude-sdk-permission-mode` or `HARNESS_CLAUDE_SDK_PERMISSION_MODE` selects another supported SDK mode. The preflight marks `auto` as provider-enforced rather than locally enforced, and `--disallow-claude-sdk-auto-permission-mode` fails before scheduling when a runtime policy does not accept that default. Invalid mode text is diagnosed by class and not echoed into artifacts.

Upgrade actions should be preceded by the local version preflight helper before any installer, package manager, or source update command is invoked. The preflight compares mocked or discovered current/latest versions locally, reports `upgrade_needed`, `already_current`, `downgrade_blocked`, `dev_version_blocked`, or `invalid_version`, and permits the action only for a newer stable version unless development or preview versions are explicitly opted in. This keeps release checks replayable in tests and prevents stale, downgrade, and preview upgrade paths from being hidden inside runner side effects.

Connector-native tool policy evaluation is fail-closed. A timeout, exception, unreachable policy service, malformed result object, or malformed `ToolCallPolicyResult` field keeps the tool out of the executable registry. DENY verdicts route to `denied`; ASK-style verdicts set `review_required` and route to `review_only` rather than executing silently.

Native harness policy-hook fixtures follow the same no-silent-allow rule for governed tool-call phases. Timeout, connection failure, and error-response cases deny the tool call. A slow ASK decision routes to `review_only` with `policy_ask_timeout`, so an operator-review path is explicit and the tool is not executed. Explicit ASK verdicts for `TOOL_CALL`, `TOOL_RESULT`, `OUTPUT`, and sub-agent start phases are preserved as `review_required` with a body-free controller surface. They remain pending until a fixture supplies an explicit `approval_resolution` of `approved` or `denied`; unknown phases keep the fail-closed denial behavior.

Workspace changes-panel fixtures validate changed-file evidence without exporting raw paths or file bodies. Required native, external-process, and filesystem-endpoint edits must have visible panel entries; visible changed-file entries must map back to performed edits; and path evidence for a matched edit must agree by hash. When a fixture provides a `runner_workspace_root`, required edits and visible changed-file panel entries must be inside that runner workspace; the evaluator exports only root/path hashes and failure classes, not raw paths. Missing entries, stale path evidence, unexpected extra entries, and outside-runner-workspace entries are distinct failure modes so stale, overbroad, or misplaced workspace detection cannot pass as a green e2e runner signal.

Mock LLM workflow fixtures that model a REPL or e2e approval journey can set `native_tool_policy.approval_expected`. When this contract is present, a governed tool-call step must produce a review-required approval path; a missing or stale policy verdict is reported as `approval_path_missing` even if the mock response and tool-call-name contract otherwise look green. Fixtures can also declare `native_tool_policy.approval_output_poll` with a bounded timeout, interval, expected marker, and recorded output samples. The evaluator deterministically replays those samples until the expected approval marker appears or the timeout is exhausted, so tests do not depend on a single immediate REPL-output read. Raw tool arguments, session IDs, tool names, and approval-output bodies remain omitted or hashed; a missing marker fails as `approval_output_poll_timeout`.
An explicit operator denial counts as a resolved approval path for this mock
governance contract, but it keeps `tool_executed: false` and does not become an
allowed execution path. This lets local approval-denial journeys pass as
deterministic safety-preserving mock routes instead of being misreported as a
missing approval prompt.

Approval surfacing regressions should be tracked by phase before changing runtime behavior. `docs/upstream-evidence-interpretation.md` records the Omnigent PR #764 watch item for INPUT, TOOL_CALL, TOOL_RESULT, OUTPUT, and sub-agent ASK phases, with privacy-leakage cases kept review-only and future local tests limited to body-free metadata such as phase names, booleans, failure classes, counts, and hashes.

### Promotion Gate

After a successful Codex pass, the supervisor may promote the candidate into `main` without human approval when all gate conditions pass:

- the candidate has a new commit
- `latest-rollback-point.json` exists
- the target worktree is clean
- candidate health commands pass
- `main` can accept the commit with `git merge --ff-only`
- post-merge health commands pass

The default health commands are `uv run pytest` and `uv run ruff check .`. If post-merge health fails, the supervisor resets the target branch back to the pre-merge HEAD and records that rollback in the pass artifact.

Successful promotions can be pushed to the configured remote. This is a runtime policy controlled by `--push-promotions/--no-push-promotions`. A successful promotion also writes `latest-activation.json` with the promoted HEAD and its previous rollback head.

### Restart Handoff

After a successful promotion, the supervisor writes `latest-restart-request.json`. Operators can run the supervisor under an outer watchdog and enable `--exit-after-promotion`; the supervisor then exits with the configured restart code so the outer process can relaunch from the latest `main`.

On process start, the supervisor runs the configured health commands before scheduling the next pass. If startup health passes, the current checkout is recorded as `latest-activation.json`; this lets manual hotfixes become the rollback baseline after verification. If startup health fails, the supervisor uses `latest-activation.json` to choose a rollback target, falling back to the last promotion's `target_before` when no activation record exists.

### Application Policy

Local source evolution does not require human approval when:

- a rollback point exists
- the change is made on a prepared evolution branch
- validation has run or a failure artifact was written
- material actions are recorded

Remote writes, deployment, and scheduler activation are runtime-policy decisions. The controller should record what it attempted, which configured capability was used, and the resulting URL or artifact.

## State

The minimum durable state:

- cursor per repository
- first-seen trend repositories
- last observed star count per trend repository
- memory statistics per repository and topic
- lesson summaries and outcomes
- digest ID
- processed event IDs
- proposal IDs
- rollback ref and rollback artifact paths
- verification result
- application decision
- Codex task path and final message path for local kernel runs
- supervisor heartbeat, pass records, candidate worktree path, promotion result, restart request, activation baseline, activation branch/HEAD, and optional local commit SHA

Store only references to runtime capabilities in repo state, never credential values or private chats.

## Failure Handling

- Empty update: write a small no-op digest or heartbeat.
- API rate limit: preserve cursor and retry later.
- Partial failure: persist the successful normalized events and mark digest incomplete.
- Verification failure: do not publish; include failure evidence.
- Post-merge health failure: reset the target branch to the pre-merge HEAD and record rollback status.
- Startup health failure after restart: reset through the latest activation baseline and record startup health status.
- Missing runtime policy: leave proposal pending or keep the local branch unapplied.

