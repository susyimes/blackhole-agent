# Skill Route Discovery

External skill repositories are evidence for local routing lessons, not skill
packages to import during the same run. Discovery records should classify the
observed repository shape into review lanes that blackhole-agent can validate
locally: documentation, config, test, or code patch.

This note is grounded in source digest `github-growth-20260618T062043.878926Z`
and the bounded evidence reviewed for this run:

- `https://github.com/baskduf/FableCodex`
- `https://github.com/dongshuyan/compass-skills`
- `https://github.com/majidmanzarpour/threejs-game-skills`

No upstream code, install scripts, prompts, or skill bodies were adopted.

## Route Matrix

| Observed repository | Evidence shape | Candidate lanes | Local lesson | Activation boundary |
| --- | --- | --- | --- | --- |
| `baskduf/FableCodex` | Codex workflow package with evidence gates, inspection, ledgers, and verification habits. | documentation, test, code patch | Treat workflow skills as process-contract evidence that can become local docs, regression checks, or bounded verification behavior. | Keep disabled until a local test or controller path proves the specific gate. |
| `dongshuyan/compass-skills` | Multi-skill system for clarification, repo-local task memory, and collaboration profile state. | documentation, config, test, code patch | Treat skill ecosystems as routing topology evidence: entry points, durable state, and ambiguity gates can inform local route metadata. | Do not create local memory/profile behavior from repository presence alone. |
| `majidmanzarpour/threejs-game-skills` | Domain director routes specialist game, asset, debug, QA, and release skills with bundled helper materials. | documentation, config, test, code patch | Treat domain directors as evidence for explicit route orchestration and validation ledgers. | Do not run bundled scaffolds, installers, browser checks, or asset generators without a separate local capability path. |

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
