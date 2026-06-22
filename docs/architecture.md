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

`agent_workflow_route` fixtures model controller-visible one-shot agent runs. When a fixture declares `oneshot_marker.required`, the evaluator checks marker presence before activation and reports `blocked_before_activation` with `oneshot_marker_missing` if the marker is absent. Marker paths are hashed rather than exported, and the evaluator does not launch or restart the runner. This gives harness evidence about absent one-shot markers a deterministic local pass/fail lane while preserving explicit supervisor control over restart and recovery.

The same route can declare `orchestrator_inbox.required` for sub-agent delivery replay. The evaluator requires exactly one completion message by default, a parent wake, non-empty child output, no transcript-only completion recovery, and non-degraded child lifecycle metadata such as present sub-agent identity, stable send handle, and close support. Message IDs, child session IDs, turn IDs, transcript bodies, and payload bodies are hashed or omitted. Missing delivery, duplicate delivery, empty turns, transcript-only completion, parent wake failure, and degraded lifecycle are distinct local failure modes. The contract also reports whether transcript polling is available only as recovery, whether child-session cleanup is required or blocked, and the operator action to replay or recover the route, so runner-control regressions can be reviewed without busy-polling a live child session as normal behavior.

The same route now emits a `runner_harness_control_plane` summary that ties intake, mid-flight state, recovery, replay, and report artifacts into one operator-visible contract. Replay and report paths are represented only by hashes. Fixtures can require an explicit recovery handoff with operator-reset commands and a replay command; the evaluator exports only command counts and hashes, and marks the recovery stage missing when a required handoff is incomplete. Fixtures can also declare observations as load-bearing or non-load-bearing; unreliable observations are allowed only when marked non-load-bearing, so flaky teardown/status probes can be recorded without becoming silent pass/fail gates. A load-bearing unreliable observation fails locally as `unreliable_load_bearing_observation`.

`agent_harness_provider_registration` fixtures validate proposed provider harness registrations before activation. A Qwencode-style provider can be represented as metadata with required commands and environment keys, then blocked as `required_provider_config_missing` when the local command or config is absent. The lane does not launch the provider, import an SDK, install packages, or expose environment values; env-key identifiers are represented by hashes in diagnostics. Use `pytest tests/test_harness_eval.py -q -k agent_harness_provider_registration` when current-wake harness evidence proposes a new provider registration path.

The same lane can replay host-registration state before provider activation. If a fixture shows that a host id is already registered to one owner but the current authenticated owner differs, or if a controller would report connection success before registration completes, the lane blocks as `host_registration_owner_mismatch` or `host_registration_incomplete_success_state`. Host ids and owner values are hashed only, provider launch remains false, and the recovery hint tells the operator to refuse the connected state until stale registration or host-id reset is handled.

`mock_llm_workflow_route` fixtures are expected to prove that the mock provider path was actually exercised. The evaluator records whether every queued mock response was consumed, and when file tools or native policy hooks are declared it checks that consumed mock turns included the required tool-call names. OpenAI-compatible mock server lanes can also declare a `/v1/chat/completions` contract: non-streaming requests must receive JSON-shaped mock responses, streaming requests must receive SSE-shaped mock responses, consumed request counts must match the workflow, and mock auth/base-url preflight failures are classified separately from mock-server contract drift. Raw tool arguments, chat messages, responses, base URLs, and token values are not exported; tool-call names used for the contract are reported by count and hash. A route that leaves responses queued, never observes a declared tool boundary, returns the wrong mock response format, or fails provider preflight fails locally instead of passing from absence of side effects alone.

`headless_tool_roundtrip` fixtures cover the narrower headless dispatch path where a model stream emits `function_call` or `tool_call` events. The local report normalizes those events, routes them through the same executable descriptor and policy checks used by the tool registry, and records whether each function call was dispatched, blocked, or missing a handler. It is intentionally dry-run only: raw event bodies and arguments are omitted or hashed, and tool callables are never executed by the harness.

`mock_e2e_runner_tier` fixtures can require an approval boundary for host-native journeys. When `approval_boundary.required` is set, the evaluator reuses the native policy-hook adapter and only passes if the mocked journey preserves an ASK/review path on the controller surface without executing the tool call. Raw commands, policy payloads, session IDs, paths, and content remain omitted or hashed.

`known_failure_metadata_preflight` fixtures run before a growth pass treats test evidence as current. The preflight compares expected and current known-failure metadata, detects absent metadata, empty current metadata, removed entries, unexplained changes, and missing gate-refresh records, then reports `test_gating_should_refresh` plus body-free recovery hints. Failure IDs are represented only as hashes, raw test names and failure text are not exported, and the lane does not edit quarantine files or execute tests. Use `pytest tests/test_harness_eval.py -q -k known_failure_metadata_preflight` when upstream push or PR activity suggests known-failure metadata was removed, repointed, or stale.

The same mock E2E lane can carry a compact single-file agent YAML document as `agent_config.yaml`. This validates YAML parsing and controller tool routing with the local single-file agent parser, but it does not execute the declared agent, import the callable, contact a provider, or require credentials. Reports include only YAML hashes, route counts, executable-tool counts, required-tool diagnostics, and hashed tool names; raw prompts, callable paths, commands, fixture paths, and YAML bodies stay out of controller output. A configured YAML route fails locally when parsing fails, no function tools are declared, required tools are missing, or parsed tools cannot reach the executable local registry.

`push_delivery_path` fixtures model the final promotion delivery handoff without performing a remote write. They require a successful promotion target, an explicitly requested push, a mocked runner command shaped like `git push <remote> <branch>`, activation and restart-request records, and rollback metadata. The evaluator fails if the route would require credentials, network, or an unmocked remote call, and it exports only booleans and hashes rather than raw remotes, branches, commands, or credential material. This gives upstream push/test activity a local regression lane while keeping actual push activation under supervisor runtime policy.

`proposal_interpretation` fixtures adapt small agent task cases into the frozen proposal interpreter. Their JSON output records review status, selected item IDs, accepted proposal IDs, validation preflight metadata, evidence-ref policy, and a compact safety-boundary summary without exporting the raw digest or model response. Accepted `evidence_refs` are checked against the supplied digest `item_id` values and the selected context item IDs, so URL citations or invented references remain rejected by local regression cases. The safety summary is metadata only: proposals flagged for offensive behavior or privacy leakage must remain `reviewable_proposal_only` behind a human-review gate, and the local adapter does not execute offensive benchmark behavior.

`provider_runtime_preflight` fixtures model provider startup without live SDK calls. They treat browser tooling such as Playwright as optional: missing browser configure support produces a degraded/skipped diagnostic, but URL safety is evaluated independently and can still block launch. Native terminal launch risks are also modeled before long sessions start: a macOS iTerm2/tmux Claude Code route whose native CLI is not visible to the runner is blocked as `native_terminal_timeout_risk`. Claude-native prompt readiness can be checked with a metadata-only `prompt_scan` block: fixtures record scan-tail limits, status-footer line counts, prompt distance, timeout seconds, whether legacy tail scanning would miss the prompt, and whether a second message would time out. Pane text is not exported. Review-model configuration can be checked with a metadata-only `review_models` block before review execution; unavailable, unsupported, missing, or required-but-unexercised model routes block as `review_model_*` failure classes. Provider wire API routing can be checked with a metadata-only `wire_api` block: `chat`, `responses`, and `completions` aliases are normalized, unsupported routes block as `provider_wire_api_unsupported`, missing required routes block as `provider_wire_api_missing`, and `wire_api: chat` must be exercised by local route evidence or it blocks as `provider_wire_api_unexercised`. Provider throttling can be replayed with a metadata-only `usage_limit` block: status 429 or exhausted `anthropic-ratelimit-unified-*` windows block as `provider_usage_limit_exhausted`, while response bodies, raw header values, reset strings, retry-after values, credential labels, and credential material are omitted or hashed. Credential-pool failover remains review-only in this lane because labels and tokens are privacy-sensitive; the preflight records that failover was not executed. This is intended for CI/review provider changes where opaque model identifiers may be renamed, unsupported by the configured gateway, temporarily unavailable due to provider limits, or wired to the wrong chat/responses route. Raw review bodies, raw model IDs, and raw provider wire API values are omitted; reports keep provider labels, normalized route enums, counts, hashes, and recovery classes. Worker-scoped env inheritance is capability-aware: if a fixture explicitly targets a `*_worker` tool and the harness declares no worker tool, the env-inherit invariant is reported as skipped instead of blocking or forcing os-env propagation. A long Claude Code status footer above a prompt should be validated with `pytest tests/test_harness_eval.py -q -k provider_runtime_preflight`, and a too-small scan window should fail as `prompt_scan_timeout_risk` before a live provider session is launched. Base URL values, CLI paths, pane text, review text, provider response bodies, rate-limit reset values, credential labels, wire API raw values, and environment values are recorded only as presence booleans, normalized integration labels, counts, hashes, and failure classes, not as raw URLs, paths, prompts, review bodies, provider bodies, credential identifiers, provider config bodies, or secrets.

`provider_runtime_recovery_summary` fixtures aggregate multiple provider-runtime preflight cases into an operator-visible recovery surface. The summary reports pass/degraded/blocked counts, blocked failure classes, runner-invocation counts, and stable recovery hint codes such as `provider_env_missing`, `native_terminal_timeout_risk`, `prompt_scan_timeout_risk`, `provider_usage_limit_exhausted`, `provider_wire_api_unexercised`, `review_model_unavailable`, `url_safety_preflight_failed`, `mock_auth_placeholder_used`, and `browser_configure_checks_skipped`. It also emits `supervisor_readiness`, a body-free handoff decision with replay commands, recovery hint codes, blocked failure classes, and explicit denial of provider runtime launch or remote execution. Usage-limit recovery tells the operator to wait for reset or route credential-pool failover through privacy review; it does not select, rank, print, or switch pooled credentials. When a configured credential pool is present, the usage-limit preflight also emits a `failover_review_plan` with safe next-action codes and local replay commands, while continuing to omit credential labels, token values, raw headers, reset values, and provider response bodies. A degraded-only summary can be ready for local replay, but it is no longer reported as supervisor promotion success: `success_status` sets `provider_runtime_degraded_replay_only`, keeps `success_claim_allowed: false`, and requires operator action while preserving `ready_for_supervisor_local_replay: true`. Blocked preflights remain blocked before supervisor promotion. It does not launch providers and does not export raw preflight inputs, diagnostics, URLs, paths, model IDs, review bodies, provider response bodies, wire API raw values, rate-limit reset values, credential labels, environment values, or environment key names. This lane is intended for locally replayable validation of mock/provider migration work where a scheduler needs the next safe local fix without inspecting provider bodies.

`rendered_html_artifact_validation` fixtures validate browser-observable HTML artifacts without exporting HTML bodies, raw URLs, snapshot paths, or image bodies. The lane checks script execution, external-link navigation, and optional UI snapshot gates. Empty landing-state snapshot gates require both baseline and current snapshot hashes plus an observed empty-state marker; missing baselines, missing current snapshots, unobserved empty states, and unapproved diffs are distinct failure modes. This turns upstream UI diff snapshot-gate signals into a replayable local validation path rather than a live browser dependency.

`skill_route_discovery_lane` fixtures replay frozen skill-route evidence through the local discovery registry and proposal lane map before activation. They verify that external skill repositories produce only documentation, config, test, or code_patch lanes; every lane keeps `runtime_action: none`; local validation remains required; and raw source/evidence URLs are hashed rather than exported. The lane also emits a body-free source-lineage summary with candidate source counts, hashed candidate and related source URLs, duplicate summary counts, evidence item ID counts, and fork/mirror collapse status so supervisors can see lineage pressure without treating upstream repositories as installable packages. Actionful discovery requests such as install, enable, run, execute, clone-and-run, or local deletion are reported as rejected candidates and no external skill code is executed.

For pass-2 skill-route windows, the same lane emits `local_lane_acceptance_contract` inside `pass2_handoff_packet`. The contract turns selected and queued route evidence into per-lane acceptance gates for bounded lane membership, local validation, no runtime action, denied external skill/harness/provider/remote execution, and omitted raw upstream evidence. This gives supervisors a direct replay contract for COMPASS-style state handoff, game/frontend skill bundles, and mixed Codex/workflow/skill evidence without treating upstream repositories as installable or executable.

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

