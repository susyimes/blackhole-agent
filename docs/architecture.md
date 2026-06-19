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

This layer is intentionally small and transparent. It biases proposal ordering toward sources and topics that have produced useful lessons before. It can be deleted without corrupting cursor state.

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

### Local Codex CLI Kernel

Runs only when explicitly selected with `--evolution-mode codex`.

The controller creates a coherent task from the digest proposals, writes a rollback point, prepares a local branch, and invokes:

```text
codex exec --cd <repo> --ignore-user-config --sandbox workspace-write --ephemeral -
```

The task is passed through stdin, and Codex writes its final response to an output artifact with `--output-last-message`.
Operators that want the autonomous loop to mutate without the Codex sandbox can pass `--bypass-approvals-and-sandbox`, which forwards Codex's explicit full-access bypass flag.

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

`mock_llm_workflow_route` fixtures are expected to prove that the mock provider path was actually exercised. The evaluator records whether every queued mock response was consumed, and when file tools or native policy hooks are declared it checks that consumed mock turns included the required tool-call names. Raw tool arguments are not exported; tool-call names used for the contract are reported by count and hash. A route that leaves responses queued or never observes a declared tool boundary fails locally instead of passing from absence of side effects alone.

`push_delivery_path` fixtures model the final promotion delivery handoff without performing a remote write. They require a successful promotion target, an explicitly requested push, a mocked runner command shaped like `git push <remote> <branch>`, activation and restart-request records, and rollback metadata. The evaluator fails if the route would require credentials, network, or an unmocked remote call, and it exports only booleans and hashes rather than raw remotes, branches, commands, or credential material. This gives upstream push/test activity a local regression lane while keeping actual push activation under supervisor runtime policy.

`proposal_interpretation` fixtures adapt small agent task cases into the frozen proposal interpreter. Their JSON output records review status, selected item IDs, accepted proposal IDs, validation preflight metadata, evidence-ref policy, and a compact safety-boundary summary without exporting the raw digest or model response. Accepted `evidence_refs` are checked against the supplied digest `item_id` values and the selected context item IDs, so URL citations or invented references remain rejected by local regression cases. The safety summary is metadata only: proposals flagged for offensive behavior or privacy leakage must remain `reviewable_proposal_only` behind a human-review gate, and the local adapter does not execute offensive benchmark behavior.

`provider_runtime_preflight` fixtures model provider startup without live SDK calls. They treat browser tooling such as Playwright as optional: missing browser configure support produces a degraded/skipped diagnostic, but URL safety is evaluated independently and can still block launch. Native terminal launch risks are also modeled before long sessions start: a macOS iTerm2/tmux Claude Code route whose native CLI is not visible to the runner is blocked as `native_terminal_timeout_risk`. Claude-native prompt readiness can be checked with a metadata-only `prompt_scan` block: fixtures record scan-tail limits, status-footer line counts, prompt distance, timeout seconds, whether legacy tail scanning would miss the prompt, and whether a second message would time out. Pane text is not exported. Worker-scoped env inheritance is capability-aware: if a fixture explicitly targets a `*_worker` tool and the harness declares no worker tool, the env-inherit invariant is reported as skipped instead of blocking or forcing os-env propagation. A long Claude Code status footer above a prompt should be validated with `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`, and a too-small scan window should fail as `prompt_scan_timeout_risk` before a live provider session is launched. Base URL values, CLI paths, pane text, and environment values are recorded only as presence booleans, normalized integration labels, counts, and failure classes, not as raw URLs, paths, prompts, or secrets.

Codex mutation uses a separate provider/config preflight before `codex exec` starts. Controller and supervisor Codex mode require an explicit `--model` or `--profile` by default, write `latest-codex-provider-preflight.json`, and include the route selector in run manifests. This prevents an unpinned agent head from silently falling through to an unintended CLI default provider; `--allow-default-codex-route` keeps the old implicit route available when an operator chooses it deliberately. The same artifact includes metadata-only ambient provider discovery: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, and `GOOGLE_APPLICATION_CREDENTIALS` are recorded as presence booleans, env-name lists, endpoint/source hints, and incomplete-credential diagnostics, never as raw token, URL, or credential-path values.

Supervisor startup preflight also records the effective Claude SDK permission mode without importing or launching the SDK. The default is `auto`, unless `--claude-sdk-permission-mode` or `HARNESS_CLAUDE_SDK_PERMISSION_MODE` selects another supported SDK mode. The preflight marks `auto` as provider-enforced rather than locally enforced, and `--disallow-claude-sdk-auto-permission-mode` fails before scheduling when a runtime policy does not accept that default. Invalid mode text is diagnosed by class and not echoed into artifacts.

Upgrade actions should be preceded by the local version preflight helper before any installer, package manager, or source update command is invoked. The preflight compares mocked or discovered current/latest versions locally, reports `upgrade_needed`, `already_current`, `downgrade_blocked`, `dev_version_blocked`, or `invalid_version`, and permits the action only for a newer stable version unless development or preview versions are explicitly opted in. This keeps release checks replayable in tests and prevents stale, downgrade, and preview upgrade paths from being hidden inside runner side effects.

Connector-native tool policy evaluation is fail-closed. A timeout, exception, unreachable policy service, malformed result object, or malformed `ToolCallPolicyResult` field keeps the tool out of the executable registry. DENY verdicts route to `denied`; ASK-style verdicts set `review_required` and route to `review_only` rather than executing silently.

Native harness policy-hook fixtures follow the same no-silent-allow rule for governed tool-call phases. Timeout, connection failure, and error-response cases deny the tool call. A slow ASK decision routes to `review_only` with `policy_ask_timeout`, so an operator-review path is explicit and the tool is not executed.

Workspace changes-panel fixtures validate changed-file evidence without exporting raw paths or file bodies. Required native, external-process, and filesystem-endpoint edits must have visible panel entries; visible changed-file entries must map back to performed edits; and path evidence for a matched edit must agree by hash. When a fixture provides a `runner_workspace_root`, required edits and visible changed-file panel entries must be inside that runner workspace; the evaluator exports only root/path hashes and failure classes, not raw paths. Missing entries, stale path evidence, unexpected extra entries, and outside-runner-workspace entries are distinct failure modes so stale, overbroad, or misplaced workspace detection cannot pass as a green e2e runner signal.

Mock LLM workflow fixtures that model a REPL or e2e approval journey can set `native_tool_policy.approval_expected`. When this contract is present, a governed tool-call step must produce a review-required approval path; a missing or stale policy verdict is reported as `approval_path_missing` even if the mock response and tool-call-name contract otherwise look green. The evaluator still omits raw tool arguments, session IDs, and tool names from exported results.

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

