# Skill Route Discovery

External skill repositories are evidence for local routing lessons, not skill
packages to import during the same run. Discovery records should classify the
observed repository shape into review lanes that blackhole-agent can validate
locally: documentation, config, test, or code patch.

This note is grounded in source digest `github-growth-20260618T062043.878926Z`,
refined by `github-growth-20260618T171207.138935Z`, clarified by
`github-growth-20260618T193207.157147Z`, reaffirmed by
`github-growth-20260618T215207.204133Z`, and extended by
`github-growth-20260618T233207.218276Z`. The bounded evidence reviewed for
these runs:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`

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

## Proposal Lane Map

The disabled discovery registry can now be rendered into a proposal-lane map.
This is the controller-facing form for local growth planning: each recognized
skill project can produce only documentation, config, test, or code_patch
proposal kinds, each with `runtime_action: none` and local validation required.

Unsupported lane hints are downgraded by removing the unsupported lanes and
recording them in `downgraded_candidates`. Candidates that request install,
enable, run, execute, clone-and-run, local deletion, private/non-plain source
URLs, or other non-lane validation failures are recorded in
`rejected_candidates` and produce no proposal lanes.

This keeps the useful lesson from the reviewed repositories: public skill
ecosystems reveal reusable routing shapes, but upstream installers, scripts,
scaffolds, profile stores, and QA helpers are evidence to inspect, not actions
to perform during discovery.

## Route-Hint Policy Preflight

Before proposal interpretation accepts any implementation lane,
`build_route_hint_policy_preflight` checks the controller-owned route-hint
policy in the frozen evidence package. For `skill_route_discovery`, the only
valid resolved lanes are still documentation, config, test, and code_patch. Any
extra lane such as runtime_execution, install, enable, or follow_up_issue causes
the preflight to fail before a candidate can be normalized or accepted.

The preflight is intentionally metadata-only. It reads selected item
`route_hints` and the controller policy table, then reports selected hints,
configured hints, resolved skill-route lanes, and diagnostics. It does not read
upstream skill bodies, install packages, expose secrets, execute repository
scripts, or add new evidence URLs. This makes route-hint drift visible even
when an LLM candidate would otherwise be rejected later by the per-candidate
lane check.

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
