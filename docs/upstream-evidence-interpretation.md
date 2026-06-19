# Upstream Evidence Interpretation

Public agent-project movement is input evidence for blackhole-agent, not direct
permission, implementation authority, or proof that a local change is safe.

This rule matters most for fast-moving repositories whose README, issues, pull
requests, and stars can signal useful engineering direction before the details
are locally verified. A trending agent harness can justify a local experiment;
it cannot authorize new runtime capabilities, remote writes, credential access,
promotion behavior, or restart activation.

## Evidence Rule

Treat each public signal as a bounded local validation candidate:

- record the source URL and the specific observed fact
- separate the upstream claim from the local hypothesis
- note when the evidence is generic, marketing-level, untitled, truncated, or
  missing implementation detail
- cite only URLs or item IDs present in the frozen digest evidence package
- do not copy upstream behavior directly when the local repository has a
  narrower policy, different runtime capability, or no matching validation lane

Low-detail upstream movement is a prompt for bounded validation, not direct
implementation evidence. Untitled pull requests, repeated generic PR lifecycle
events, generic push events, or push clusters whose commit messages do not show
clear test or CI evidence may justify documentation, tests, config preflight, or
follow-up review. They should not justify `code_patch` work until the local run
records a confirming detail such as an inspected PR body, commit diff, release
note, failing local test, or repository file that maps the upstream movement to
a specific local behavior.

The proposal interpreter may summarize and rank candidate lessons, but it must
not add evidence URLs, remove risk flags, grant permissions, or decide final
validation gates. Deterministic review and local validation keep ownership of
those decisions.

## Local Validation Lanes

Allowed lanes for upstream movement are deliberately concrete:

- documentation: explain a reusable rule, caveat, or operational contract
- test: encode the proposed behavior or boundary as a local regression case
- code patch: implement a bounded behavior change with focused verification
- config: make an explicit runtime or provider assumption inspectable
- follow-up issue: preserve a useful but under-specified lesson for review

Routes that enable offensive behavior, abuse, unauthorized access, or privacy
leakage remain review-only. Missing detail should not block every experiment,
but it must narrow the claim: prefer a reversible local validation over broad
adoption, and record uncertainty in the run artifact or proposal rationale.

## Skill Route Discovery

External skill repositories may be useful evidence for future routing behavior,
but discovery is not installation. Skill-route evidence should first be recorded
as a disabled local candidate with the source URL, observed workflow shape, the
`skill_route_discovery` hint, and only these candidate lanes: documentation,
config, test, or code patch.

The local registry shape is classification-only. It must not enable an external
skill, add executable tool routes, or treat a repository name as permission to
load code. A later change may promote a candidate only after a separate local
validation path proves the behavior and records the activation boundary.

Repository lifecycle signals do not change that boundary. A newly discovered
skill repository is recorded as `record_only_no_install`, and a deleted upstream
skill repository is recorded as `record_only_no_local_deletion`. Malformed
candidate lanes are stripped from the exported lane list and preserved only as
validation errors, so the registry output remains limited to documentation,
config, test, and code patch review paths.

## Governance Policy Route

Public agent projects that advertise policies, sandboxing, approval gates,
permission controls, spend caps, or tool limits should be classified as
`governance_policy` evidence before any local change is drafted. This route is
for local controller behavior, configuration, tests, or documentation; it does
not grant new runtime authority, remote execution, credential access, restart
activation, or live policy changes.

`governance_policy` proposals may use only documentation, config, test, or code
patch lanes. Follow-up-only or runtime-expansion proposals from the same
evidence should be rejected or narrowed until a focused local validation path is
available.

## Agent Harness Eval Route

Public agent-harness repositories can justify a local eval lane when the
evidence names replayable stages, deterministic controls, structured artifacts,
fixtures, or validation behavior. The local lane is `agent_harness_eval`: it may
produce only documentation, test, or code patch proposals, and it must keep
external harness execution out of scope until a separate runtime capability and
validation path exist.

Security-adjacent harness evidence, including vulnerability discovery,
adversarial verification, exploit validation, or unauthorized-access context,
is boundary evidence. It can be recorded as a review note, but it must not
activate offensive behavior, remote scans, credential use, or external harness
execution. Use item IDs from the frozen digest in fixtures and comments; export
source URL hashes or counts rather than raw upstream URLs from local harness
eval reports.

## Omnigent Upstream Movement Watchlist

Source digest: `github-growth-20260618T175207.227269Z`.

Watch `https://github.com/omnigent-ai/omnigent` for controller, runner, harness,
and review workflow movement, but keep each signal in an evidence tier before it
changes local behavior.

High-detail signals are actionable only as bounded local validation candidates:

- PR bodies or commit messages that name a concrete controller, runner, or
  harness interface, such as `HarnessDescriptor`, `NativeServerHarness`, native
  server transport, terminal takeover, or sub-agent harness override
- explicit policy or safety changes, especially allowlist-gated runtime
  overrides, fail-closed permission decisions, sandbox isolation, spend limits,
  or approval gates
- review outcomes that include a concrete blocking finding, fixed file path,
  affected behavior, and follow-up test or deferral rationale
- test evidence that names the covered matrix, such as conformance parity,
  transport contracts, permission mapping, forwarder translation, UI picker
  coverage, or full-suite counts
- explicit deferrals that explain why a migration is not behavior-preserving or
  not safely landable in the same change

Weak signals are activity evidence, not implementation evidence:

- untitled pull request metadata
- generic merged, opened, closed, labeled, or pushed events without an inspected
  body, commit message, diff, test result, or review finding
- review anchors where GitHub exposes only "left review comments", "found
  potential problems", "fixed", or an error while loading the review body
- large size labels by themselves
- repository star, fork, issue, or PR counts without a mapped local hypothesis

Before adopting upstream behavior locally, run this checklist:

- cite the exact evidence URL from the frozen digest and record whether it is
  high-detail or weak
- separate the upstream observation from the local hypothesis
- compare the proposed behavior with this repository's current controller,
  runner, tool-routing, provider-preflight, and harness-validation contracts
- require a focused local validation lane: documentation for interpretation
  rules, tests for boundaries, config for explicit runtime assumptions, or code
  only when a concrete local behavior and rollback path are covered
- keep remote execution, credential access, promotion, push, restart, cloud
  sandbox, and live policy changes out of scope unless a later run has explicit
  local configuration and validation for that capability

Evidence reviewed for this watchlist:

- `https://github.com/omnigent-ai/omnigent` presents a meta-harness over Claude
  Code, Codex, Cursor, Pi, and custom agents, with policies, sandboxing,
  approval gates, spend caps, shared sessions, server/host workflows, and cloud
  sandbox options.
- `https://github.com/omnigent-ai/omnigent/pull/576#pullrequestreview-4527267074`
  points at a detailed OpenCode harness and unified harness-interface PR. The
  visible PR text names a controller/runner-relevant abstraction, optional
  workers, allowlist-gated `args.harness`, permission-policy fail-closed fixes,
  model pinning, environment isolation, concrete tests, and deferred migration
  rationale.
- The same review URL only partially exposes bot review comments in this run;
  those review anchors are useful watchlist prompts, but not enough to copy a
  patch without inspecting the specific finding or proving the local boundary.

## Claude-Native Prompt Scan Regression

Source digest: `github-growth-20260618T181207.161132Z`

The Omnigent issue `https://github.com/omnigent-ai/omnigent/issues/701`
describes a Claude-native second-message timeout when prompt readiness scans
only the last few non-empty terminal lines and a rendered status footer pushes
the prompt outside that tail window. This is a concrete upstream bug report, so
the local lesson is an executable preflight lane rather than a broad runtime
copy.

For this repository, provider prompt scanning assumptions are modeled in
`provider_runtime_preflight` fixtures with body-free metadata: configured tail
lines, legacy tail lines, non-empty status-footer line count, prompt distance
from the bottom, timeout seconds, and whether a second message would time out.
The validation command is `pytest tests/test_harness_eval.py -q -k
provider_runtime_preflight`. Troubleshooting a long Claude status footer should
raise the configured scan-tail limit or block launch with
`prompt_scan_timeout_risk` before trying a live provider session. Raw terminal
pane text, prompts, paths, URLs, environment values, tokens, and credentials
must not be exported.

## Provider Runtime Recovery Handoff

Source digest: `github-growth-20260619T203207.276361Z`.

Public provider and harness projects show useful runtime patterns, but local
startup remains gated by metadata-only preflight. Each
`provider_runtime_preflight` result now carries a body-free `recovery_hints`
list and `supervisor_replay` block so a blocked provider can be diagnosed from
the individual preflight output, not only from an aggregate recovery summary.

Use the individual preflight when the operator needs the first failure reason
for one provider route, such as missing model command metadata, missing
provider environment propagation, unsafe browser URL, review-model
unavailability, prompt-scan timeout risk, or native terminal launch risk. Use
`provider_runtime_recovery_summary` when multiple preflights must be grouped
into status counts and deduplicated hint codes.

The recovery summary separates local replay readiness from success. A degraded
mock-auth or optional-tooling route may be replayable, but it is still reported
as `provider_runtime_degraded_replay_only` with `success_claim_allowed: false`
and `provider_runtime_launch_allowed: false`. This prevents a scheduler from
treating body-free diagnostics as a successful provider launch or promotion.

Both surfaces are replay-only. They may expose hint codes, affected harness
labels, counts, replay commands, and boolean launch decisions. They must not
export raw model commands, prompt bodies, review output, terminal panes, URLs,
paths, environment values, token names with values, credentials, or secrets.
`provider_runtime_launch_allowed` remains false until a separate runtime
capability and validation path explicitly permits launch.

## Approval ASK Surfacing Watch

Source digest: `github-growth-20260619T035206.981359Z`

The Omnigent pull request
`https://github.com/omnigent-ai/omnigent/pull/764` re-filed eight quarantined
approval e2e tests under a non-INPUT ASK surfacing issue. The PR describes a
metadata-only test quarantine change: INPUT-phase approval tests passed, while
TOOL_CALL, TOOL_RESULT, OUTPUT, and sub-agent-tunneled ASK cases failed
consistently. The upstream note separates phases that may be intentional
collapse-to-DENY behavior from phases that look like surfacing bugs, and it
keeps the entries quarantined pending a product decision.

For this repository, the reusable watch item is phase-specific approval
surfacing, not Omnigent's quarantine file format. If similar failures appear
locally, inspect these subsystems before proposing a behavior patch:

- approval e2e and mock workflow fixtures that expect an explicit
  review-required path
- manual/local mode handling where a provider or runner might silently collapse
  ASK into DENY or allow
- test-branch and known-failure metadata that can make a stale green result
  look like a working approval path

The first local validation lane should be documentation or tests. A runtime
change requires a local failing case that distinguishes INPUT, TOOL_CALL,
TOOL_RESULT, OUTPUT, and sub-agent ASK phases without exporting raw prompts,
tool arguments, session identifiers, private chats, tokens, credentials, or
other personal data. Privacy-leakage scenarios remain review-only; they may
record metadata such as phase names, booleans, failure classes, counts, and
hashes, but not sensitive bodies.

## Evidence From This Run

The source digest cited `https://github.com/omnigent-ai/omnigent`. Its public
README presents a multi-agent harness with policies, sandboxing, spend limits,
and scoped governance for server, agent, or chat contexts. The reusable lesson
for this repository is not to adopt that implementation directly, but to keep
public agent-project movement behind explicit local policy, citation, and
validation boundaries.

The same digest stream included low-detail movement around Omnigent PRs and
pushes. Those signals are evidence that the project is active, but their titles
and generic event summaries do not reveal enough implementation shape to support
copying a behavior. In this repository they should narrow the route toward
local confirmation first: inspect the bounded evidence, record uncertainty, and
only draft a `code_patch` after a concrete upstream detail or local failing test
supports the proposed behavior.
