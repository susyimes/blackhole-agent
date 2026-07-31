# Architecture

## Objective

Build an agent that periodically tracks public GitHub trends and converts them into useful, rollback-backed local improvements. The agent should learn from the broader ecosystem while leaving enough artifacts to audit and recover its autonomous changes.

## Components

### Unbound Single-Agent Runtime

`blackhole_agent.unbound` is an independent long-horizon path. One logical agent
owns one durable mission, one resumable CLI session, and one persistent mission
worktree. It does not consume the generated GitHub-growth proposal pipeline and
does not create child agents. Turns may preserve unfinished changes without
committing; only demonstrated capability milestones receive controller commits.
The fresh-process run loop reloads worker code from the mission worktree so the
agent can change its own controller for subsequent turns. The complete contract
is documented in `docs/unbound-v2.md`.

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

### Evolution Route and Capability Compounder

The legacy `skill_route_discovery` lane pipeline (classifier, route profiles,
bounded local-apply lanes, focused-validation cascades, and residual-adjacent
pin/cascade packaging) has been removed. Digests no longer emit
`skill_route_discovery_capability_pipeline`; there is no skill-route lane,
operator-state, or continue-cascade surface left in the runtime.

Every digest instead carries a compact `evolution_route` surface built by
`blackhole_agent.evolution_route`:

- when the durable capability ledger (`capabilities/ledger.json`) is ready, the
  surface is a redirect that freezes skill-route pin/cascade expansion and
  points the supervisor next action at capability prove/compose/demo
- when the ledger is not ready, the same surface reports `ledger_not_ready`
  with `grow_capability_ledger_first` as the next action instead of building
  proposal lanes

Growth compounds through the Capability Compounder
(`blackhole_agent.capability_compounder`): capabilities are registered with an
invocable proof command, proved, composed into multi-capability units, and
stored in the durable ledger. The supervisor's codex wakes redirect to the
compounder by default once the ledger is ready; `--prefer-legacy-growth` or
`BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE=1` selects the plain digest/plan path,
which still cannot emit skill-route lanes.

Proposal route hints are reduced to two bounded classes,
`provider_config_preflight` and `governance_policy`, each mapped only to
documentation/config/test/code_patch lanes. Public agent-project movement
remains trend evidence only; see `docs/upstream-evidence-interpretation.md`
for the bounded local validation candidate contract. The historical record of
the removed pipeline is summarized in `docs/skill-route-discovery.md`.

### Capability Theme Window

Memory keeps a compact theme window (`memory.theme_window`) that gives
consecutive self-evolution passes a shared capability target: theme id, the
active capability slice, planned pass count, anchoring proposal IDs, and
evidence URLs. It biases proposal ordering only; it carries no lane machinery.

### Selectable Local CLI Kernel

Runs only when explicitly selected with `--evolution-mode codex`. The `--kernel codex|grok|kimi` selector chooses the local execution backend without changing the surrounding rollback and promotion protocol.

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

The Kimi route uses the native non-interactive and machine-readable contract:

```text
kimi --output-format stream-json --prompt <task>
kimi --session <session-id> --output-format stream-json --prompt <next-task>
```

The controller extracts `session.resume_hint` from the stream and resumes that
native session for later Unbound turns. Prompt text is stored in a task artifact
and redacted from recorded command artifacts, although the native Kimi CLI still
receives it as a command-line argument. Native prompt mode is inherently
fully automatic and rejects `--auto`, `--plan`, and `--yolo`; the preflight
blocks those incompatible combinations. Proposal interpretation therefore uses
an explicit non-mutation prompt contract rather than a CLI plan flag.

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

Runs local checks for any generated patch or config change. A failed
verification produces a digest entry and stops the write path. The default
health commands are `uv run pytest` and `uv run ruff check .`; the supervisor
runs them on the candidate before promotion and again after merge.

Durable verification lives in the capability ledger:

- every capability carries an invocable `proof_command`; `blackhole-unbound
  capability prove <id>` re-runs it together with its dependencies
- the ablation proof is falsifiable: it mutates a scratch copy of the ledger,
  breaks proofs and dependency chains, and requires verification to fail
- outcome contracts are adversarially checked: must-pass and must-fail
  predicates both gate evaluator honesty
- the harness activation gate (`harness_activation_gate_decision` in
  `blackhole_agent.capability_compounder`) is a native local-eval-only
  decision: only the clean `none` failure mode activates, and external harness
  execution is never allowed
- the grounded growth chain is hermetic: payload -> hypotheses -> scan ->
  implementation trace -> patch, re-verified from sealed artifacts with
  tamper-falsification checks
- the plane engine proves its full layer stack against hermetic golden digests

Local fixture comparisons remain body-free: prompts, outputs, and stdout/stderr
bodies are omitted or represented by stable hashes, and privacy-flagged
material stays review-only.

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

