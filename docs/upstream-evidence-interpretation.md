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

## Evidence From This Run

The source digest cited `https://github.com/omnigent-ai/omnigent`. Its public
README presents a multi-agent harness with policies, sandboxing, spend limits,
and scoped governance for server, agent, or chat contexts. The reusable lesson
for this repository is not to adopt that implementation directly, but to keep
public agent-project movement behind explicit local policy, citation, and
validation boundaries.
