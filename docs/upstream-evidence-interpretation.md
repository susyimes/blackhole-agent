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
