# Skill Route Discovery

External skill repositories are evidence for local routing lessons, not skill
packages to import during the same run. Discovery records should classify the
observed repository shape into review lanes that blackhole-agent can validate
locally: documentation, config, test, or code patch.

This note is grounded in source digest `github-growth-20260618T062043.878926Z`,
refined by `github-growth-20260618T171207.138935Z`, clarified by
`github-growth-20260618T193207.157147Z`, reaffirmed by
`github-growth-20260618T215207.204133Z`, and extended by
`github-growth-20260618T233207.218276Z`. The source digest
`github-growth-20260619T001207.230597Z` rechecked the same route class and
added the requirement that selected digest `item_id` values remain visible in
item-derived lane maps. Source digest `github-growth-20260620T005207.516587Z`
extended the replay fixture to the current four carried skill evidence items,
including fork-lineage evidence, while preserving selected `item_id` citations
instead of URL citations. The bounded evidence reviewed for these runs:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/pretinhuu1-boop/threejs-game-skills`
- `https://github.com/xiaoguomeiyitian/threejs-game-skills`

No upstream code, install scripts, prompts, or skill bodies were adopted.

The 2026-06-18T21:52Z wake rechecked the same public repository class and kept
the lesson narrow. FableCodex describes Codex workflow gates, COMPASS Skills
describes local skills for clarification, task memory, and collaboration
profiles, and Three.js Game Skills describes a domain director with specialist
skills and verification helpers. Those are useful routing shapes, but the local
artifact remains documentation and fixture coverage only. The evidence does not
grant permission to install, execute, scaffold, profile, generate assets, or
activate any upstream skill package.

## Route Matrix

| Observed repository | Evidence shape | Candidate lanes | Local lesson | Activation boundary |
| --- | --- | --- | --- | --- |
| `baskduf/FableCodex` | Codex workflow package with evidence gates, inspection, ledgers, and verification habits. | documentation, test, code patch | Treat workflow skills as process-contract evidence that can become local docs, regression checks, or bounded verification behavior. | Keep disabled until a local test or controller path proves the specific gate. |
| `dongshuyan/compass-skills` | Multi-skill system for clarification, repo-local task memory, and collaboration profile state. | documentation, config, test, code patch | Treat skill ecosystems as routing topology evidence: entry points, durable state, and ambiguity gates can inform local route metadata. | Do not create local memory/profile behavior from repository presence alone. |
| `majidmanzarpour/threejs-game-skills` | Domain director routes specialist game, asset, debug, QA, and release skills with bundled helper materials. | documentation, config, test, code patch | Treat domain directors as evidence for explicit route orchestration and validation ledgers. | Do not run bundled scaffolds, installers, browser checks, or asset generators without a separate local capability path. |

## Route Discovery Catalog

The reusable lesson is a category map, not a source import. A future digest may
observe more skill repositories than the three above, but each observation must
be translated through one of these local routes before proposal synthesis uses
it:

| Category | Recognition hints | Allowed local outputs | Required validation | Rejected shortcut |
| --- | --- | --- | --- | --- |
| Workflow-gate package | Evidence gates, review ledgers, inspection habits, verification routines, Codex or agent workflow language. | documentation, test, code_patch | Show the local gate in docs or a focused regression before changing runtime behavior. | Installing the upstream workflow or treating its README as proof the local controller already behaves that way. |
| State and alignment skill system | Task memory, collaboration profile, clarification gate, repo-local task graph, route metadata, skill ecosystem map. | documentation, config, test, code_patch | Keep state body-free unless a later local design explicitly models storage, retention, correction, and privacy boundaries. | Creating profile or memory behavior from repository presence alone. |
| Domain director or specialist bundle | Director skill, specialist skills, scaffold, packaged helpers, QA scripts, asset or browser validation workflow. | documentation, config, test, code_patch | Validate only the local orchestration or boundary being changed; treat bundled scaffolds and helpers as evidence to inspect. | Running installer, scaffold, browser checker, asset generator, credential probe, or helper script during discovery. |

Catalog entries are additive only when they preserve the same bounded outputs:
documentation, config, test, or code_patch. Any proposed lane outside that set
is recorded as rejected or downgraded evidence, never as an activation request.

## Classification Rules

Record a candidate as `skill_route_discovery` when the digest evidence shows a
public repository organized around reusable agent skills, directors, workflows,
or skill installation. The first local artifact should be body-free metadata:
name, source URL, short evidence summary, route hint, candidate lanes, validation
status, and disabled state.

Source URLs must be plain public GitHub repository URLs. The classifier rejects
local paths, non-HTTPS schemes, private hostnames, owner-only GitHub URLs, and
URLs carrying query strings, fragments, embedded credentials, or other
decorations. Discovery metadata is intended to be replayable public evidence,
not an intake path for private locations, tokens, or installable package bodies.

Allowed candidate lanes are exactly:

- documentation
- config
- test
- code_patch

Blocked discovery actions include install, enable, run, execute,
clone-and-run, and local deletion. Repository lifecycle events remain record
only: creation does not install a skill, and deletion does not delete a local
skill.

Fork or mirror evidence is lineage evidence, not independent activation
pressure. When a body-free repository summary carries `upstream_source_url`,
`forked_from_url`, or `parent_source_url`, summary classification groups the
candidate by the upstream public GitHub repository and records the related
public source URLs for audit. The duplicate fork does not increase
`candidate_count`, proposal lane count, activation lane candidate count, or the
readiness of a local proposal. This keeps a repeated public skill package from
amplifying one lesson merely because it appears under more than one repository
owner.

Repeated public activity around the same skill repository name can now affect
only local discovery selection and metadata. Repository trend, fork, and push
items that classify as `skill_workflow` are grouped by a body-free project key
before context truncation. When two or more selected activities point at the
same project, the selector gives that skill-route evidence a small bounded
confidence bump and `build_route_hint_lane_map` reports a
`route_activity_pressure` summary with hashed project keys, item IDs, event
kinds, allowed lanes, local validation requirement, and `runtime_action: none`.
This is intended for repeated COMPASS Skills-style trend, fork, and push
pressure: it can make documentation, config, test, or code_patch investigation
more likely to survive context budgeting, but it does not create install,
enable, clone, run, execute, deletion, provider launch, remote execution, or
external skill activation authority.

The local harness also exposes that movement as `activity_signal_panel`.
GitHub `PushEvent` values are normalized to `push` and interpreted only as
validation pressure for the four bounded local lanes. A COMPASS Skills-style
push can therefore produce documentation, config, test, and code_patch rows,
but every row keeps `runtime_action: none`, requires the normal local replay
commands, hashes source metadata, and denies external skill activation,
external harness execution, provider launch, remote execution, and raw upstream
body export. Push movement never means install, enable, execute, clone, profile
write, memory write, or deletion.

Low-detail pull request movement is visible in the same panel only as weak
supporting context until a separate local corroboration record exists. Generic
or untitled `PullRequestEvent` evidence, missing PR details, lifecycle-only
summaries, route hints, CI words, and candidate lane names are not enough to
make a lane activation-ready. The panel records
`generic_movement_policy: supporting_context_only_until_local_corroboration`,
`weak_generic_movement_count`, and row-level
`weak_generic_supporting_context_only: true` while the activation gate remains
`review_weak_evidence_before_activation`. When a focused fixture, local
validation command, artifact, or operator review note corroborates the generic
movement, the policy can become `locally_corroborated_generic_context`; even
then, the lane remains limited to documentation, config, test, or code_patch
and keeps external skill activation denied.

The harness also emits `generic_validation_prompt` for that state. It is an
operator-facing prompt, not a proposal proof: it lists the low-detail PR rows,
accepted local corroboration signal kinds, replay commands, and the current
activation decision while denying runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw evidence URL
export, source URL export, and upstream body export. This keeps Omnigent-style
generic PR movement useful as a validation target without treating an untitled
pull request as behavior-change evidence.

## Review Notes

The evidence is repository-level and README-level. That is enough to preserve a
route-discovery matrix and local fixture, but not enough to promote a candidate
to executable skill routing. A future code patch should cite a narrower local
failure, test gap, or inspected upstream detail before changing runtime behavior.

## Acceptance Criteria

`skill_route_discovery` is accepted only when it stays inside the discovery
lane. A valid local change must satisfy all of these criteria before it can be
treated as more than evidence:

- Provenance: cite only frozen digest evidence or derived item evidence already
  present in the run package; do not trust README claims as implementation
  parity.
- Scope: map the discovery route only to documentation, config, test, or
  code_patch work.
- Local tests: add or run validation sized to the local artifact being changed;
  repository popularity or external examples do not replace local tests.
- Rollback: record a rollback ref or artifact before self-modification and keep
  recovery explicit.
- Trust boundary: do not automatically import, install, enable, execute, clone,
  scaffold, or otherwise trust external skill code from discovery evidence.
- Privacy boundary: do not expose, print, upload, publish, or share tokens,
  credentials, secrets, private keys, private chats, PII, or personal data while
  evaluating skill repositories.

## Summary Fixture Lane

Synthetic repository summaries can now be classified into the same disabled
registry without requiring pre-shaped candidate metadata. This lane is
body-free: the classifier reads public source URL, name, short summary, topics,
event kind, and optional suggested lanes, then emits only disabled
`skill_route_discovery` records.

Summary classification may narrow or expand local validation work only across
the bounded lanes: documentation, config, test, and code_patch. Suggested lanes
such as install, execute, run, or runtime execution are ignored rather than
promoted into candidate lanes or requested actions. Non-skill repositories are
ignored, and URL validation still happens at registry build time.

## Issue Evidence Lane

Repository issues can refine the same disabled discovery candidate when they
carry an explicit `skill_route_discovery` hint and body-free title or summary
evidence about a skill or workflow route. Issue URLs are canonicalized back to
their repository for candidate grouping, while the original issue URL is kept as
deduplicated evidence.

Repeated issue evidence increments duplicate counts instead of creating another
candidate, requested action, or executable route. Issue-derived lanes remain
bounded to documentation, config, test, and code_patch; install, execute, run,
and other runtime lanes are ignored during classification.

Issue and repository evidence items also preserve a separate
`evidence_item_urls` list. Proposal lanes rendered from an item-derived registry
cite only those frozen item URLs, even when broader candidate metadata contains
extra URLs. Summary-only registries keep the older repository-level fallback
because they do not carry per-item provenance.

Item-derived registries also preserve selected digest `item_id` values in
`evidence_item_ids`. Duplicate evidence URLs are still counted as duplicates and
do not create extra candidates, URLs, lanes, or summaries, but their distinct
selected `item_id` values are retained so proposal review can trace a lane back
to the frozen digest selection set.

## Proposal Lane Map

The disabled discovery registry can now be rendered into a proposal-lane map.
This is the controller-facing form for local growth planning: each recognized
skill project can produce only documentation, config, test, or code_patch
proposal kinds, each with `runtime_action: none` and local validation required.
The lane map also carries `candidate_lane_inventory`, one compact row per
recognized or downgraded candidate, so an operator can inspect which bounded
local lanes came from each public skill repository before reading the expanded
proposal rows. Inventory rows repeat the activation boundary:
`local_validation_required: true`, `runtime_action: none`,
`external_skill_activation_allowed: false`, and
`activation_gate: local_validation_before_activation`.
Each lane also carries body-free uncertainty text and `uncertainty_reasons` so
review can distinguish repository-level trend evidence, sparse selected-item
evidence, fork or mirror amplification, and `missing_detail_risk` from locally
validated behavior. These fields are review metadata; they do not grant external
skill activation or replace the required local validation commands.
When the source registry was built from selected evidence items, each lane also
exports the preserved `evidence_item_ids`; these ids are provenance only and do
not add new evidence or actions.

The harness exposes that inventory as `candidate_lane_intake` before the
expanded lane matrix. This is an operator-facing candidate selection surface,
not an activation surface. Each row hashes the candidate name and source,
reports bounded local proposal kinds, route profiles, selected digest item IDs,
evidence URL hashes, downgraded lane pressure such as `install`, `execute`, or
`runtime_execution`, and rejection counts. A `ready` intake means every candidate
mapped cleanly to documentation, config, test, or code_patch lanes and the
activation gate is already open for local proposal work. A `review` intake means
the candidate inventory remains body-free and locally bounded but downgraded or
rejected upstream pressure must be reviewed before a supervisor selects a local
validation lane. The intake always keeps `runtime_action_allowed: false`,
`external_skill_activation_allowed: false`, `external_skill_code_allowed: false`,
and raw source or evidence URLs out of the harness result.

Each intake row also includes `recommended_local_lane_order`, a profile-specific
ordering of only the lanes already present for that candidate. FableCodex-style
workflow gates prefer replay/test or documented-gate work first; COMPASS-style
state handoff routes prefer config or documentation boundary metadata before
tests or code patches; Three.js-style game director routes prefer validation
and documentation before local code changes. The recommendation never adds a
lane, never overrides downgraded or rejected upstream pressure, and never
permits install, enable, run, execute, clone-and-run, scaffold, asset
generation, provider launch, profile writes, memory writes, or external skill
activation.

The harness also emits `term_route_review`, a compact body-free panel for the
literal route-trigger terms `agent`, `agents`, `codex`, `skill`, `skills`, and
`workflow`. Each row is keyed by hashed candidate and source identifiers,
reports the matched terms and already-bounded proposal kinds, and rechecks that
local validation is required, `runtime_action` is `none`, external skill
activation is false, and raw source, evidence, or upstream bodies are not
exported. This panel is diagnostic only: repository popularity or term matches
can explain why evidence entered skill-route discovery, but they do not add
lanes, cite new evidence URLs, or make install, enable, run, execute,
clone-and-run, scaffold, profile-write, provider-launch, or external skill
activation requests valid.

Unsupported lane hints are downgraded by removing the unsupported lanes and
recording them in `downgraded_candidates`. Candidates that request install,
enable, run, execute, clone-and-run, local deletion, private/non-plain source
URLs, or other non-lane validation failures are recorded in
`rejected_candidates` and produce no proposal lanes.

This keeps the useful lesson from the reviewed repositories: public skill
ecosystems reveal reusable routing shapes, but upstream installers, scripts,
scaffolds, profile stores, and QA helpers are evidence to inspect, not actions
to perform during discovery.

## Local Harness Lane

`skill_route_discovery_lane` is the local harness behavior for replaying frozen
skill-route evidence before activation. It accepts body-free evidence items,
repository summaries, or pre-shaped candidates, builds the disabled discovery
registry, and renders the proposal lane map through the same bounded lane
contract: documentation, config, test, and code_patch.

The harness output is metadata-only. It reports candidate counts, lane counts,
proposal kinds, downgrade/rejection counts, whether every lane keeps
`runtime_action: none`, whether every lane requires local validation, a
body-free `evidence_strength` summary, body-free uncertainty reasons, and an
`activation_gate` for the controller surface. Generic pull request or push clusters are
`weak_generic_upstream_movement` unless the fixture also carries a separate
body-free `local_corroboration` record. A route hint, CI word, test word, or
generic PR title inside the upstream evidence does not count as corroboration
by itself. Weak generic movement can support investigation, documentation, or
review notes, but it is not activation-ready merely because its candidate lanes
are otherwise bounded.
Clean evidence is
`ready_for_local_proposal_activation`; downgraded evidence is
`review_degraded_lane_before_activation`; rejected or empty evidence is
`blocked_before_activation`; weak generic upstream movement is
`review_weak_evidence_before_activation`; generic upstream movement with local
corroboration can become `ready_for_local_proposal_activation`. The gate always
keeps `external_skill_activation_allowed: false`; it can only permit local
proposal activation for clean or locally corroborated documentation, config,
test, or code_patch lanes. Raw source and evidence URLs are hashed rather than
exported. Requested activation actions such as install, enable, run, execute,
clone-and-run, or local deletion block the harness lane as rejected candidates
and do not execute.

The same local harness family now includes a metadata-only CI round-trip
diagnostic for mocked E2E runner lanes. When public harness evidence suggests a
CI prompt round-trip is hanging, the local fixture should classify that as
`ci_round_trip_hang` separately from `authentication_failure`. The diagnostic
records only the expected and observed failure families, prompt/completion
booleans, and body-free privacy flags; it must not export raw CI logs, command
strings, token names with values, credentials, or provider responses.

The harness also renders a `discovery_checklist` for operator review before
local activation. Each checklist row records the hashed source, capability,
allowed local lane, required tests, rollback note, runtime action, and external
activation flag. The row is intentionally bounded: source URLs are represented
as hashes, capability is `skill_route_discovery`, allowed local lane is one of
documentation, config, test, or code_patch, required tests include
`pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane`, rollback
notes require a rollback ref and artifact before source changes, runtime action
remains `none`, and external skill activation remains false.

The same output includes an `evidence_lane_matrix` for source-by-source review.
Each row hashes the candidate name and source URL, lists only the bounded local
lanes derived from that source, records selected digest item IDs and hashed
evidence URLs, reports downgraded or rejected lane pressure, and keeps
`runtime_action: none`. This matrix is intended for cases such as COMPASS
Skills, Three.js Game Skills, and FableCodex where upstream repositories may
mention installers, scaffolds, plugins, credential probes, or execution helpers.
Those signals can justify local documentation, config, test, or code_patch
work, but the matrix keeps install, enable, run, execute, clone-and-run,
provider launch, remote execution, raw upstream body export, and external skill
activation denied before supervisor promotion.

Each checklist row and activation row also carries
`inspection_requirements`. This is the bounded local inspection contract for
mapping a public skill repository into work: selected digest item IDs or frozen
digest evidence, body-free repository summaries, source-lineage metadata, local
artifact targets, changed-file review, focused local validation, rollback
artifact, and review note. The same contract records blocked shortcuts:
installing upstream skills, running upstream skill code, clone-and-run behavior,
trusting a README as local implementation parity, or exporting raw upstream
bodies. The preactivation trust boundary rejects activation rows that omit or
weaken this inspection contract.

The harness now also emits a body-free `source_lineage` summary and carries a
compact lineage view into supervisor readiness. This records candidate source
counts, hashed candidate and related source URLs, duplicate summary counts,
evidence item ID counts, and whether fork or mirror lineage was collapsed. It
does not export raw source URLs or related source URLs. This keeps public
skill-pack evidence such as COMPASS Skills, Three.js Game Skills, or FableCodex
fork movement visible as lineage pressure while preserving the preactivation
rule: forked or domain-specific skill repositories can justify bounded local
documentation, config, test, or code_patch lanes, but they do not add install,
clone, run, scaffold, profile, asset-generation, provider-launch, or remote
execution authority.

For controller handoff, the harness also emits `activation_lanes`. These rows
group proposal lanes by local output kind and carry the required validation
command, candidate names, hashed candidate sources, readiness flag, blockers,
body-free recovery hint codes, runtime action, raw-source export denial, and
external activation flag. A lane is
`activation_ready: true` only when the overall gate is
`ready_for_local_proposal_activation`; weak generic evidence, downgraded lanes,
rejected candidates, unbounded lanes, missing validation, or requested runtime
action keep the row present but blocked. Blocked rows expose
`recovery_hint_codes` that point back to the harness recovery hints, so an
operator can see whether to add local corroboration, review downgraded lanes,
remove actionful metadata, or regenerate activation rows. This lets a
supervisor promote validated documentation, config, test, or code_patch work
without treating an external skill repository as an installable package.

Each activation row also carries a `local_artifact_contract`. This is a
body-free handoff target, not a write instruction from the upstream repository:
documentation lanes point at local route documentation, config lanes at local
proposal-policy code, test lanes at local route and harness tests, and
code_patch lanes at the local skill-routing or harness evaluator modules. The
pre-activation trust boundary rejects artifact targets that are URLs, absolute
paths, path traversal, non-local review surfaces, raw upstream bodies, or
external skill code. This gives a supervisor an operator-visible lane-to-file
contract before activation while preserving the rule that discovery never
imports, runs, or clones external skill packages.

The harness also emits an `implementation_intake_preflight` before supervisor
promotion. This preflight is the implementation-facing summary of the
activation rows: it reports `ready` only when the preactivation trust boundary
passed, every activation lane is ready, every proposal kind remains one of
documentation, config, test, or code_patch, and each lane still points at a
local artifact contract. It exports target paths only as hashes, requires
changed-file review and local validation, and keeps runtime action, external
skill activation, external skill code, and raw upstream bodies denied. A
blocked intake preflight means route discovery may remain useful evidence, but
it is not yet a local implementation lane.

Each activation row also carries a `provider_runtime_preflight` contract. This
does not launch a provider or execute a remote runner. It requires the local
`provider_runtime_preflight` and `provider_runtime_recovery_summary` replay
lanes before supervisor promotion, keeps diagnostics body-free, and records
`provider_runtime_launch_allowed: false` and `remote_execution_allowed: false`.
The pre-activation trust boundary rejects rows that omit this contract, weaken
the replay commands, export non-body-free diagnostics, or allow provider runtime
launch. This connects skill-route discovery to the provider/runtime control
slice: public skill evidence can become local documentation, config, test, or
code_patch work only after the same local provider diagnostic lane remains
replayable.

Activation rows also expose `provider_runtime_control`, a compact replay
handoff for the same contract. It records the provider/runtime controller
surface, replay commands, readiness decision, next safe action,
recovery hint count, recovery hint codes, and hashed hint codes without
exporting raw preflight inputs or diagnostics. A ready local artifact lane may
be replayed locally, but provider launch and remote execution remain denied; a
blocked lane keeps the same recovery hint codes visible for operator review and
points the operator toward resolving those hints before replaying provider
runtime preflight.
When the block came from a sampled provider/runtime replay, the same control
object uses `reason: provider_runtime_replay_not_ready`,
`provider_runtime_replay_blocked: true`, and a provider-replay-specific next
action so the operator can distinguish runtime diagnostic recovery from a
generic skill-route evidence or artifact blocker without seeing provider bodies.

The activation rows now also include a pre-activation local harness check. Before
promotion, the controller-visible validation set includes both the
`skill_route_discovery_lane` replay, the `agent_harness_eval_lane` replay, and
the proposal-interpretation smoke suite.
The latter is metadata-only and keeps `external_harness_execution_allowed:
false`; it exists to prove that a skill-route proposal lane can pass through the
same local harness evidence surface used for public agent-harness lessons before
activation. Checklist rows expose the same `preactivation_harness` value and
external-harness denial so an operator can distinguish local replay from remote
or upstream harness execution.

When a skill-route fixture carries `provider_runtime_preflight_samples`, the
local lane also samples the provider/runtime recovery summary before activation.
The sample is metadata-only: it exports preflight counts, status counts,
blocked failure modes, recovery hint codes and hashes, supervisor decision, and
replay commands, but not raw preflight inputs, diagnostics, source URLs, paths,
environment keys, credentials, provider bodies, or upstream skill bodies. A
blocked or degraded provider/runtime replay sample blocks local skill-route
promotion with `provider_runtime_replay_not_ready` until the recovery hints are
resolved and `provider_runtime_preflight` plus
`provider_runtime_recovery_summary` are replayed.

The harness also emits a top-level `provider_runtime_diagnostic_panel`. This is
the operator-visible replay summary for the provider/runtime control slice. It
counts ready and blocked activation lanes, checks that every lane still carries
the provider/runtime preflight contract, repeats the local replay commands,
hashes recovery hint codes, and records whether diagnostics remain body-free.
The panel never exports raw provider inputs, diagnostics, source URLs, target
paths, credentials, or upstream skill bodies. A ready panel means the local
replay commands are the next validation step before promotion; it does not
permit provider launch, remote execution, external skill activation, or
installation.

The harness also emits a `preactivation_trust_boundary` result. This is a
second, runtime-facing guard over the generated activation rows: it rechecks
that every lane remains one of documentation, config, test, or code_patch; that
runtime action is still `none`; that local validation and the pre-activation
harness replay are still required; and that external skill or harness execution
is still denied. A static registry entry is therefore not enough by itself to
make a lane activation-ready.

For supervisor handoff, the same output now includes `supervisor_readiness`.
This is a compact operator-visible decision derived from the activation gate,
activation lanes, recovery hints, and preactivation trust boundary. It reports
`ready_for_supervisor_promotion` only when every local lane is ready, all replay
commands are present, the trust boundary passed, runtime action remains denied,
and external skill or harness activation remains false. Downgraded evidence is
`review_before_supervisor_promotion`; rejected, empty, weak, or trust-boundary
failed evidence is `blocked_before_supervisor_promotion`. The summary carries
only lane counts, proposal kinds, recovery hint codes, and replay commands; it
does not export raw evidence URLs or upstream skill bodies, and it does not
request restart, remote activation, installation, cloning, or execution.

The final local handoff view is `operator_handoff`. It is derived from
`implementation_intake_preflight`, `supervisor_readiness`, activation lanes, and
body-free source lineage. It groups ready local artifact lanes by proposal kind,
exports only target path hashes and source counts, repeats the required replay
commands, and carries recovery hint codes for blocked or degraded lanes. A ready
handoff means the supervisor may review local documentation, config, test, or
code_patch artifacts; it still denies runtime action, external skill activation,
external harness execution, provider launch, remote execution, raw evidence
export, raw source URL export, and raw target path export. A blocked handoff
keeps the discovery useful as evidence but requires review or replay before any
local implementation lane is promoted.

The same lane also emits `operator_recovery_plan`, a compact replay decision for
blocked or degraded skill-route diagnostics. It converts recovery hints into
body-free recovery steps, stable hint-code hashes, local replay commands, and
the next safe action for an operator or supervisor. The plan never exports raw
evidence, source URLs, upstream bodies, target paths, credentials, provider
diagnostics, or command bodies, and it continues to deny runtime action,
external skill activation, external harness execution, provider launch, and
remote execution. A ready plan means local replay may continue; a blocked plan
means the recovery hints must be resolved before promotion.

Before that final handoff, the harness now emits `local_lane_intake`. This is
the operator-visible inventory of bounded local work inferred from external
skill evidence. It groups proposal rows by documentation, config, test, or
code_patch, exposes only hashed candidate names, hashed source URLs, hashed
local target paths, evidence item counts, inspection requirements, required
local validation commands, activation blockers, source-lineage counts, and the
discovery actions that stay blocked. It does not export raw URLs, raw target
paths, raw evidence, upstream skill bodies, or external code, and it keeps
install, enable, run, execute, clone-and-run, and deletion authority denied.
Empty or actionful evidence therefore produces no intake rows even when the
upstream repository looked like a useful skill package.

The harness also emits `route_triage_plan`, a body-free lane planning view for
operators. It converts external skill evidence into the four permitted local
lanes and records why each lane exists: documentation records route lessons and
acceptance criteria, config registers bounded policy or proposal mapping, tests
replay the route evidence locally, and code_patch changes only local
classifier, harness, or controller behavior. Each row carries hashed source
URLs, evidence item counts, uncertainty reasons, local artifact contracts,
inspection requirements, required validation commands, activation readiness, and
local artifact proof readiness. It does not export raw evidence, raw source
URLs, raw target paths, upstream skill bodies, or external code, and it keeps
runtime action and external skill activation denied. A ready triage plan means
the lane can be locally reviewed and validated; supervisor handoff can still be
blocked later when local artifact proof is missing.

The discovery lane also emits a body-free `route_profile_catalog` and repeats
bounded `route_profiles` on proposal and triage rows. Current profiles include
`codex_workflow_gate` for FableCodex-style workflow gates,
`skill_ecosystem_state_handoff` for COMPASS-style state, memory, profile, and
handoff systems, `game_frontend_workflow` for Three.js or browser game director
skills, and `generic_skill_workflow` when the evidence is too broad for a more
specific profile. These profiles are triage metadata only: they count and group
local validation candidates, keep `runtime_action: none`, require local
validation, and do not create install, scaffold, asset-generation, browser-run,
profile-writing, provider-launch, remote-execution, or external skill activation
authority.

The harness also emits `route_profile_review` before supervisor promotion. This
panel groups the proposal lanes by profile and records profile-specific
recognition signals, expected metadata, safe local tests, and rejection
conditions without exporting raw source URLs or upstream skill bodies. It is an
operator-facing inspection surface for deciding whether a route profile has
enough local evidence to become documentation, config, test, or code_patch work.

The current profile contracts are:

- `codex_workflow_gate`: FableCodex-style Codex workflow evidence. It expects
  selected digest item IDs, a body-free workflow summary, and a local gate or
  test target. It rejects upstream workflow installation, URL-based proposal
  citations, and README claims treated as local gate parity.
- `game_frontend_workflow`: Three.js game director and specialist-skill
  evidence. It recognizes browser-game, director, QA, screenshot, and canvas
  validation signals, but rejects upstream scaffolds, browser checkers,
  credential probes, provider launch, and asset generation without a separate
  local capability path.
- `skill_ecosystem_state_handoff`: COMPASS-style task clarification, memory,
  handoff, and profile systems. It expects a body-free ecosystem summary plus
  state-retention and privacy boundaries, and rejects profile or memory writes
  inferred only from repository presence.

A ready `route_profile_review` means the local route profile has an inspectable
contract for bounded local work. It still keeps `runtime_action: none`, requires
local validation, denies external skill activation, and does not import, run,
clone, install, scaffold, probe credentials, launch providers, or generate
assets from the upstream repository.

The profile review also checks body-free metadata coverage for each profile
before activation review. A FableCodex-style workflow gate must show selected
digest item IDs, a body-free workflow summary, and a local gate or test target.
A Three.js game workflow must show a body-free game-skill summary, a local
frontend validation target, and an asset/provider boundary note. A
COMPASS-style state handoff route must show a body-free skill ecosystem
summary, state-retention and privacy boundary evidence, and any local memory or
profile target as metadata only. The panel exports counts and stable hashes for
evidence records and source references, but not raw evidence text, raw source
URLs, raw target paths, upstream skill bodies, or install commands. Missing
profile metadata changes the review panel to `review` with
`metadata_missing` diagnostics; it does not create install, enable, run,
profile-write, memory-write, scaffold, browser-run, asset-generation,
provider-launch, remote-execution, or external skill activation authority.

For COMPASS-style `skill_ecosystem_state_handoff` routes, profile review now
also emits `state_handoff_preflight`. This preflight is required before a
state/profile route can be ready: the local input must explicitly record that
retention policy is documented, privacy boundaries are documented, and any
local memory or profile target is metadata-only. Repository presence, README
claims, install instructions, or skill names never grant state, memory, or
profile write authority. If the explicit boundary is absent or claims upstream
presence grants writes, the profile review stays in `review` with
`state_handoff_preflight` diagnostics while keeping runtime action, external
skill activation, raw upstream body export, and private context export denied.

The profile review now also renders `local_lane_contracts` for each bounded
proposal kind present in the profile. These contracts expose only hashed local
artifact targets, target counts, required local artifact proof fields, and the
same runtime/external-skill denials. They are the operator-visible bridge from
profile evidence to local work: FableCodex-style workflow gates, COMPASS-style
state handoff systems, and Three.js-style director bundles can point reviewers
toward local documentation, config, test, or code_patch files, but the review
surface still withholds raw target paths and upstream bodies and requires
changed-file review, focused local validation, rollback artifact, and review
note proof before supervisor handoff.

Pass-3 replay also emits `preactivation_lane_selection`, a compact selector
that chooses one bounded local lane per ready route profile from the lanes
already present in the activation manifest. FableCodex-style workflow gates and
Three.js game director routes prefer the replay/test lane first, while
COMPASS-style state handoff routes prefer config metadata before documentation,
tests, or code patches. The selector never adds a lane, never selects a profile
whose metadata review or state-handoff preflight is not ready, and never selects
without local artifact proof. It exports only route profile names and bounded
lane names, keeps `runtime_action_allowed: false`, and continues to deny
external skill activation, external skill code, external harness execution,
provider launch, remote execution, raw source URLs, raw target paths, and
upstream bodies.

On final scheduled passes for this capability slice, the harness emits
`capability_window_completion`. This panel consumes the route profile review,
activation manifest, operator handoff, supervisor readiness, and
provider-runtime diagnostic panel, then reports whether the skill-route
discovery window is complete enough for supervisor handoff. It records the
theme, current and total pass counts, hashed anchoring proposals, hashed
evidence URLs, bounded proposal kinds, route profiles, required validation, and
provider-runtime replay commands. A ready completion panel means the four-pass
slice has an operator-visible local result; it does not grant runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw evidence URL export, raw source URL export, or upstream body
export.

Final passes may also declare `required_route_profiles` in the capability
window. When present, completion checks those required profiles against the
body-free profiles actually replayed in the local harness. A pass that cites or
anchors FableCodex, COMPASS Skills, and Three.js Game Skills can therefore
require `codex_workflow_gate`, `skill_ecosystem_state_handoff`, and
`game_frontend_workflow` before supervisor handoff. Missing profiles block only
the completion handoff; they do not grant install, enable, run, execute,
clone-and-run, profile-write, memory-write, scaffold, asset-generation,
provider-launch, remote-execution, raw evidence export, raw source URL export,
or upstream body export authority.

The same panel includes `completion_handoff`, a compact supervisor-facing
contract for the final slice state. It repeats the completion status and
decision, names a `supervisor_next_action`, records the
`activation_sequence_status`, records whether the final planned pass was
observed, lists selected item-id evidence refs, and carries any
completion blockers. Ready handoffs use
`handoff_completed_skill_route_slice_to_supervisor`; non-final clean passes use
`continue_capability_window_before_completion`; blocked final passes use
`replay_or_repair_before_supervisor_handoff`. The handoff remains body-free:
selected item IDs are allowed, while raw evidence URLs, source URLs, upstream
bodies, runtime action, external skill activation, provider launch, and remote
execution remain denied.

The completion handoff also carries `completion_recovery`, a body-free repair
selector for final-pass failures. It maps existing completion diagnostics to the
next bounded local action: continue the window when the planned pass is not
complete, repair missing required route profiles, repair local artifact proof,
replay provider-runtime preflight, repair profile metadata, or replay the
bounded skill-route lane. The selector records only bounded lane names, missing
route profile names, blocker hashes, hint codes, and replay commands. It does
not export raw evidence URLs, raw source URLs, raw target paths, or upstream
bodies, and it continues to deny runtime action, external skill activation,
external harness execution, provider launch, and remote execution.

Final-pass completion now also emits `activation_packet`, a body-free supervisor
replay packet derived from the activation manifest. The packet lists only
bounded local proposal kinds, route profiles, selected item-id evidence refs,
hashed candidate sources, hashed local target paths, local artifact proof
readiness, required validation commands, and provider-runtime replay commands.
Ready packets mark each row for bounded local review and replay; blocked
packets mark rows for repair before replay. The packet does not add lanes and
does not permit install, enable, run, execute, clone-and-run, profile-write,
memory-write, scaffold, asset generation, provider launch, remote execution,
raw evidence URL export, raw source URL export, raw target path export, or
upstream body export.

Provider-runtime-control capability windows now also require a body-free
`provider_runtime_preflight_samples` replay before the completion panel can
continue. Missing samples produce `provider_runtime_preflight_sample_missing`
and route recovery to the local provider-runtime preflight and recovery-summary
commands. A ready sample is still metadata-only: it reports counts, statuses,
failure classes, hashes, and replay commands while denying provider launch,
remote execution, raw preflight input export, diagnostics export, and provider
value export. A degraded-only sample, such as a mock provider path using
placeholder auth, is ready for local replay but not ready for supervisor
promotion; the sample gate records `degraded_replay_only: true`,
`ready_for_supervisor_promotion: false`, and `success_claim_allowed: false` so
operators can replay recovery without mistaking a degraded provider diagnostic
for activation success. Blocked samples still stop completion as
`provider_runtime_replay_not_ready`. Skill-route-only windows keep the sample
optional so older discovery passes remain replayable unless a window explicitly
opts into provider-runtime control.

Before the final planned pass, the same panel reports `status: in_progress`
when all bounded lane surfaces are otherwise ready but the capability window has
not reached its planned completion count. That state carries
`capability_window_not_at_final_pass` as the only diagnostic and uses
`continue_capability_window_before_completion` as the decision, so supervisors
can keep the slice active without mistaking a healthy pass-3 replay for a
blocked route. It preserves the same documentation, config, test, and
code_patch lane bounds and the same denials for runtime action, external skill
activation, provider launch, remote execution, raw evidence URLs, raw source
URLs, and upstream bodies.

The completion panel also emits `next_pass_handoff` for pass-to-pass
continuity. This body-free handoff records the current pass, next pass,
remaining pass count, hashed candidate and source identifiers, selected item-id
evidence refs, observed route profiles, proposal kinds, and a
`recommended_local_lane_order` derived only from already bounded local lanes.
Clean non-final passes use `continue_bounded_lane_validation_next_pass` and
`continue_skill_route_discovery_window`; blocked passes use
`repair_current_pass_before_continuing`. The handoff is not an activation
surface: it repeats local validation requirements and denies runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw evidence URLs, raw source URLs, and upstream bodies.

The harness also emits `route_discovery_catalog`, an operator-visible catalog
that connects each observed route profile to the bounded local lane selected for
review. Catalog rows carry selected item IDs, hashed candidate sources,
allowed local lanes, the chosen local lane, required validation commands, and
provider-runtime replay commands. In `provider-runtime-control` windows the
catalog requires a body-free provider-runtime preflight sample before it can be
ready. The catalog is not a permission surface: it keeps runtime action,
external skill activation, external harness execution, provider launch, remote
execution, raw source URLs, raw target paths, and upstream bodies denied.

The evaluator also emits `validation_lane_plan`, a pass-to-pass operator panel
derived from the catalog. It turns each cataloged route profile into the next
bounded local validation lane, records the selected item IDs and hashed
candidate sources that justify the lane, and sets a local-only validation scope
such as `local_test_lane_only` or `local_config_lane_only`. Non-final passes use
`continue_bounded_local_validation_lane` so the supervisor can continue the
skill-route window with a concrete lane target instead of treating public skill
repositories as installable or executable workflows. The plan repeats the same
runtime, external activation, provider launch, remote execution, raw evidence
URL, raw source URL, raw target path, and upstream body denials.

The same plan also groups selected profiles into `lane_validation_targets`.
These rows are the operator-visible workload for the next pass: each row names
one bounded local lane, the route profiles it covers, selected item IDs, hashed
candidate sources, required validation commands, and provider-runtime replay
commands. A COMPASS-style state-handoff route can therefore remain a local
config validation target while FableCodex-style workflow gates and Three.js game
skill routes share a local test validation target. The grouping does not add
lanes and does not authorize upstream install, clone, execution, scaffold
generation, provider launch, remote execution, raw source URL export, raw target
path export, or upstream body export.

`capability_window_completion` now repeats those grouped targets through
`validation_target_handoff`. This makes the next supervisor action visible from
the completion surface itself: a non-final pass can carry a local config target
for COMPASS-style state handoff and a local test target for FableCodex-style or
game-skill workflow evidence without requiring operators to infer the route from
raw upstream URLs. The handoff remains body-free and keeps the same denials for
runtime action, external skill activation, external harness execution, provider
launch, remote execution, raw evidence URLs, raw source URLs, raw target paths,
and upstream bodies.

Before supervisor promotion, the lane now emits
`activation_manifest` as a compact replay surface for bounded local work. The
manifest lists only the allowed local lane names, selected-item `evidence_refs`,
route profiles, candidate source hashes, local target path hashes, local
artifact proof readiness, required validation commands, provider-runtime replay
commands, recovery hint codes, and activation blockers. Its
`evidence_ref_mode` is `selected_item_ids_only`: public repository URLs remain
source evidence in the frozen package, not manifest citations. A ready manifest
means documentation, config, test, or code_patch lanes have enough local proof
to replay; it still denies runtime action, external skill activation, external
harness execution, provider launch, remote execution, raw evidence URLs, raw
source URLs, raw target paths, and raw upstream bodies.

The activation manifest also carries `activation_sequence`, an ordered
supervisor replay checklist derived from the same body-free fields. The sequence
requires source-lineage inspection, bounded local lane checks, local artifact
proof, focused local validation, provider-runtime preflight replay, and the
final operator handoff before it reports ready. Each step repeats the denials
for runtime action, external skill activation, external harness execution,
provider launch, remote execution, raw evidence export, raw source URL export,
raw target path export, and upstream body export. The sequence is a replay
surface only; it does not install, clone, execute, scaffold, generate assets, or
activate upstream skill code.

Activation rows now distinguish bounded upstream evidence from proof that a
local artifact exists for the lane. A clean discovery lane can still be blocked
from supervisor handoff until it carries a body-free `local_artifact_proof` for
each proposal kind. That proof records only changed-file hashes, rollback
artifact hash, validation-command match, target-contract match, and a review-note
presence flag. It must not export raw upstream bodies, raw source URLs, secrets,
or external skill code, and it does not execute any upstream package. This keeps
repositories such as FableCodex, COMPASS Skills, and Three.js Game Skills useful
as route evidence while requiring an operator-visible local docs/config/test/code
artifact before promotion.

Use this lane when a digest proposes skill-route discovery work that should be
validated by the controller surface before a code, config, test, or
documentation proposal is applied:

```bash
pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane
pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane
pytest tests/test_harness_eval.py -q -k proposal_interpretation
pytest tests/test_harness_eval.py -q -k provider_runtime_preflight
pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary
```

The proposal-interpretation smoke suite is required because it checks the
controller-facing proposal gates that sit immediately after route discovery:
allowed local lanes, selected-item `evidence_refs` rather than URL citations,
and review-only classification for offensive-behavior or privacy-leakage
signals. Passing route discovery alone does not prove those proposal gates.

## Native Session Title Lane

The 2026-06-19 source digest carried Omnigent issue #851, where a native Claude
Code session launched first through a Skill or slash-command stayed untitled and
the sidebar fell back to the generic provider label `Claude Code`. The reusable
local lesson is not provider-specific UI behavior; it is a runner-harness
metadata invariant: a skill-first native session must preserve enough command,
skill, prompt, or launch context to seed a descriptive session title.

`native_skill_session_title` is the local replay lane for that invariant. It
accepts body-free fixture metadata for provider label, launch context,
transcript item kinds, and session title metadata. It passes only when a
skill/slash-command-first launch has context signals, the session title is
present, the title source is one of command, skill, prompt, launch_context, or
LLM summary, and the title does not fall back to a generic provider label.

The lane is metadata-only. It hashes title and provider labels, does not export
raw command text, prompt bodies, title strings, session IDs, or transcript
bodies, and does not launch a native provider. A blocked result should be fixed
by preserving launch context through the controller/session metadata path before
activation, then replayed with:

```bash
pytest tests/test_harness_eval.py -q -k native_skill_session_title
```

## Route-Hint Policy Preflight

Before proposal interpretation accepts any implementation lane,
`build_route_hint_lane_map` renders controller-owned route hints into bounded
proposal lanes, and `build_route_hint_policy_preflight` checks that map. For
`skill_route_discovery`, the only valid resolved lanes are still documentation,
config, test, and code_patch. Any extra lane such as runtime_execution,
install, enable, or follow_up_issue causes the preflight to fail before a
candidate can be normalized or accepted.

The lane map and preflight are intentionally metadata-only. They read selected
item `route_hints` and the controller policy table, then report selected hints,
configured hints, route-hint entries, proposal lanes, and diagnostics. They do
not read upstream skill bodies, install packages, expose secrets, execute
repository scripts, grant permissions, or add new evidence URLs. This makes
route-hint drift visible even when an LLM candidate would otherwise be rejected
later by the per-candidate lane check.

The proposal evidence package now also records a body-free route classification
beside each selected item. Public repositories that show reusable skills,
skill packs, director skills, workflow gates, workflow routing, plugins, or
tool integrations are classified as `skill_workflow` and may expose only the
bounded `skill_route_discovery` lanes: documentation, config, test, and
code_patch. General agent-project movement remains visible as
`general_agent_project` when it names agents or runtimes but lacks a skill or
workflow-specific route signal. That class does not inherit
`skill_route_discovery` lanes merely from repository popularity or generic
agent activity.

`build_route_hint_lane_map` summarizes those classifier rows through
`route_class_counts` and `route_classifier`. The rows carry item IDs, route
class, route hints, allowed local lanes, and classifier reasons only. They do
not export raw upstream bodies, add evidence URLs, grant permissions, install
packages, or request runtime action.

For general agent projects such as Omnigent-style agent frameworks or
meta-harnesses, the same lane map emits `general_agent_project_eval`. This is
an evaluation lane, not a skill-route lane: it records selected item IDs, hashed
source URLs, `agent_harness_eval_required`, allowed local lanes of
documentation, test, or code_patch, and replay commands for the local harness
and proposal tests. It keeps `skill_route_discovery_inherited: false`,
`runtime_action: none`, raw source URL export denied, and external agent
activation denied. A general agent framework can therefore justify local
harness evaluation before a behavior change, but cannot become a skill
discovery candidate unless the selected evidence also shows skill/workflow
signals.

Mixed Codex/workflow/skill repositories now get an explicit local probe before
that split becomes ambiguous. When a selected item has skill-route evidence and
also mentions Codex, plugins, examples, tests, evals, replay, harness, or other
validation signals, `build_route_hint_lane_map` emits
`mixed_skill_workflow_probe` and marks the classifier row with
`route_probe_decision: skill_route_discovery_first`. This is the FableCodex
procedure for source digest `github-growth-20260620T175208.289414Z`: public
evidence showed a Codex workflow plugin with verification habits, examples,
tests/evals, and routing docs, so the local first lane is still
`skill_route_discovery`, not upstream plugin install and not automatic
agent-harness activation.

The probe is body-free and cites only selected item IDs plus source URL hashes.
Its secondary lane is
`agent_harness_eval_after_local_corroboration`, meaning harness evaluation can
be selected later when the proposal names a general agent-project claim or when
local fixtures prove a harness-specific gap. Until then, the allowed local
outputs remain documentation, config, test, and code_patch; runtime action,
external skill activation, external agent activation, raw source URL export,
upstream body export, install, enable, run, execute, clone-and-run, profile
write, and memory write remain denied.

The mixed probe now carries an explicit activation gate:
`local_skill_route_validation_before_secondary_harness_eval`. Candidate rows
mark the secondary lane as `blocked_until_local_corroboration` and expose a
recommended local lane order of test, documentation, config, then code_patch.
That order is advisory only and is filtered to the already allowed
skill-route lanes; it cannot add follow-up issue, runtime execution, install,
provider launch, remote execution, profile-write, memory-write, raw source URL
export, or upstream body export authority. The required validation commands
remain the local mixed-skill and route-hint lane-map tests.

The `agent_harness_eval_lane` replay now carries a body-free
`claim_evaluation` matrix for this general-agent path. Each recognized public
record can contribute behavior claims such as multi-agent orchestration, policy
or sandbox control, provider configuration, conversation state, or local data
grounding. Claims that map to existing local controller or runner capabilities
name their focused validation commands; claims without a local capability remain
`unmapped_evidence_only`. The matrix does not export raw repository URLs or
upstream bodies, does not execute external projects, and does not grant external
agent activation. This is the intended lane for comparing Omnigent-style
meta-harness evidence with domain-agent evidence such as xuefeng-agent before
any local behavior change is proposed.

## Evidence Citation And Uncertainty

When `skill_route_discovery` appears in a frozen proposal evidence package,
proposal examples and replay fixtures must cite only selected `item_id` values
in `evidence_refs`. They must not cite repository URLs, owner/repository names,
truncated item IDs, or evidence URLs invented by the candidate. The deterministic
review layer derives accepted evidence URLs from those frozen `item_id` values.

Focused replay checks for this route should assert both halves of the contract:
accepted candidates use only documentation, config, test, or code_patch lanes,
and every accepted `evidence_ref` is a selected `item_id` from the frozen
evidence package. URL strings such as `https://github.com/baskduf/FableCodex`
are valid source evidence in the package, but they are not valid proposal
citations.

Trend-only repository details are enough to select a bounded local lane, but not
enough to claim upstream implementation parity. When the selected evidence is
generic, README-level, sparse, or context-budget truncation reports
`missing_detail_risk`, proposal uncertainty must mention that missing detail
risk and narrow the claim to local validation.

Example accepted citation shape:

```json
{
  "proposal_id": "skill-route-doc-contract",
  "kind": "documentation",
  "evidence_refs": ["fablecodex-codex-skill-workflow"],
  "uncertainty": "Repository-level trend evidence leaves missing_detail_risk for specific upstream implementation details."
}
```

Example rejected citation shape:

```json
{
  "proposal_id": "skill-route-url-citation",
  "kind": "documentation",
  "evidence_refs": ["https://github.com/baskduf/FableCodex"],
  "uncertainty": "This cites a URL instead of a frozen item_id."
}
```
