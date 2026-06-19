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
item-derived lane maps. The bounded evidence reviewed for these runs:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`
- `https://github.com/pretinhuu1-boop/threejs-game-skills`

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
Each lane also carries body-free uncertainty text and `uncertainty_reasons` so
review can distinguish repository-level trend evidence, sparse selected-item
evidence, fork or mirror amplification, and `missing_detail_risk` from locally
validated behavior. These fields are review metadata; they do not grant external
skill activation or replace the required local validation commands.
When the source registry was built from selected evidence items, each lane also
exports the preserved `evidence_item_ids`; these ids are provenance only and do
not add new evidence or actions.

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

For controller handoff, the harness also emits `activation_lanes`. These rows
group proposal lanes by local output kind and carry the required validation
command, candidate names, readiness flag, blockers, body-free recovery hint
codes, runtime action, and external activation flag. A lane is
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
