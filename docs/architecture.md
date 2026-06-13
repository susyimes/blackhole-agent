# Architecture

## Objective

Build an agent that periodically tracks public GitHub trends and converts them into useful, reviewable improvement proposals. The agent should learn from the broader ecosystem without becoming an uncontrolled self-modifying system.

## Components

### Scheduler

Runs the intake job once per hour. It owns the last-seen cursor and should never assume the previous run completed successfully unless the digest was persisted.

Recommended first choice:

- GitHub Actions or another hourly scheduler for a read-only trend scanner.

Alternative choices:

- Local daemon for private workstation experiments.
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

The filter must explain why an event was selected or ignored.

### Learning Digest

Writes a bounded hourly digest:

- new facts
- reusable implementation patterns
- risks or regressions
- candidate actions
- evidence links
- confidence and urgency

The digest should be small enough for humans and agents to review.

### Proposal Generator

Turns high-value digest entries into candidate improvements:

- documentation update
- test addition
- config change
- code patch draft
- follow-up issue
- "do nothing" decision

The default output is a proposal, not a push.

### Local Codex CLI Kernel

Runs only when explicitly selected with `--evolution-mode codex`.

The controller creates a bounded task from the digest proposals, writes a rollback point, prepares a local branch, and invokes:

```text
codex exec --cd <repo> --sandbox workspace-write --ask-for-approval never --ephemeral -
```

The task is passed through stdin, and Codex writes its final response to an output artifact with `--output-last-message`.

The kernel is intentionally local:

- no automatic push
- no automatic PR creation
- no Linear writes
- no policy or credential changes
- no schedule changes

### Rollback Gate

Before any self-evolution branch is prepared, the controller records:

- original branch
- original HEAD
- local rollback ref
- pre-run dirty status
- explicit recovery commands

The rollback point is written to `latest-rollback-point.json` and `latest-rollback-point.md` in the run output directory. It is the universal recovery path if a future activation fails to start or behaves unsafely.

Rollback execution is intentionally not automatic because it uses destructive commands such as `git reset --hard` and `git clean -fd`. A human operator or external supervisor must choose it.

### Verification Gate

Runs local checks for any generated patch or config change. A failed verification produces a digest entry and stops the write path.

### Approval Gate

Required for:

- pushing branches
- opening pull requests
- writing Linear comments
- changing schedules
- changing policy
- changing credential scopes
- modifying the agent's own code

## State

The minimum durable state:

- cursor per repository
- first-seen trend repositories
- last observed star count per trend repository
- digest ID
- processed event IDs
- proposal IDs
- rollback ref and rollback artifact paths
- verification result
- approval decision
- Codex task path and final message path for local kernel runs

Do not store tokens, raw secrets, or private chats in repo state.

## Failure Handling

- Empty update: write a small no-op digest or heartbeat.
- API rate limit: preserve cursor and retry later.
- Partial failure: persist the successful normalized events and mark digest incomplete.
- Verification failure: do not publish; include failure evidence.
- Missing approval: leave proposal pending.

