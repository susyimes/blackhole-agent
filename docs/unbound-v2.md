# Unbound v2

`blackhole-unbound` is the single-agent, long-horizon evolution runtime. It is a
separate path from `github_growth`; trend digests, capability-theme pass counts,
skill-route pipelines, and the legacy self-model are not injected into Unbound
turns.

## Runtime Contract

One mission owns:

- one persistent goal and outcome-level `done_when`
- one branch and long-lived sibling Git worktree
- one Codex or Grok session resumed between turns
- one durable `state.json` and append-only `events.jsonl`
- zero child agents, delegated workers, or parallel task schedulers

The goal may be supplied by the operator. If it is omitted, the first turn is a
genesis turn: the agent inspects the repository, selects a high-impact mission,
and writes both the goal and its completion contract into durable state.

State lives under:

```text
.blackhole-agent/unbound/
  latest-mission.json
  missions/<mission-id>/
    state.json
    events.jsonl
    turns/<number>/
      prompt.md
      final-message.md
      turn.json
      kernel/
```

The working repository lives in a sibling directory rather than inside the
state tree. This lets incomplete work survive process restarts without leaving
the controller checkout dirty.

## Turn Contract

Every turn receives only the durable mission, current Git state, recent compact
turn summaries, and pointers to local state. Repository details are inspected
on demand. The legacy generated pipeline is never copied into the prompt.

The single agent returns one JSON decision:

- `continue`: retain unfinished work and run another turn without a controller commit
- `milestone`: record a demonstrated, reusable capability increment
- `complete`: record the final milestone and close the mission because `done_when` is met
- `blocked`: preserve all work and stop until the mission is explicitly resumed

An accepted milestone requires all of:

- at least one repository change since the previous milestone
- at least one changed behavior path outside docs, tests, artifacts, and controller state
- a non-empty description of the capability delta
- concrete outcome evidence
- an exact validation command with exit code `0`
- `done_when_met=true` when the requested status is `complete`

If any condition is missing, the requested milestone is downgraded to
`continue`. The work remains in the mission worktree; no artificial checkpoint
commit is created.

## Authority

Unbound runs the selected CLI kernel in its full-access mode. The agent may:

- rewrite or delete existing code and generated architecture
- add or replace dependencies
- use network research and installed tools
- run local services and end-to-end experiments
- change Git history on its mission branch or use configured remotes
- modify its own prompt, planner, evaluator, and Unbound implementation

This authority is not converted into mandatory activity. A turn may continue
without committing, and a mission may use one turn or many. Passing tests and
adding documentation are supporting evidence, not capability growth by
themselves.

Grok is configured with memory enabled, web search enabled, full workspace
access, and `--no-subagents`. Codex runs with a durable JSON session and full
access. Both session types are resumed on later turns.

## Self-Reload

The default `run` loop starts each tick in a fresh Python interpreter with
`PYTHONPATH` pointing at the evolving mission worktree. Changes to
`blackhole_agent.unbound` therefore affect the next turn without requiring the
stable outer scheduling process to import mutated modules in place.

When the controller itself has not yet been committed to the selected base
branch, the first tick falls back to the invoking checkout. As soon as the
mission worktree contains `blackhole_agent.unbound`, later ticks load that
evolving copy.

Use `--keep-controller-loaded` only for debugging when this self-reload behavior
is not wanted.

## Continuous Self-Evolution

The outer continuous loop starts a new autonomous-genesis mission after the
previous mission completes or blocks. Mission-internal turns remain
back-to-back; the outer interval applies between missions and retry attempts.
The default interval is 1800 seconds (30 minutes):

```bash
uv run blackhole-unbound loop \
  --repo-path . \
  --kernel grok \
  --interval-seconds 1800
```

The first mission starts immediately unless `--wait-first` is supplied. After a
mission records accepted milestones, the next mission is based on its latest
proven milestone commit rather than resetting to `main`. An active latest
mission is resumed after a controller restart. This produces one serial
single-agent lineage; it does not introduce child agents or parallel work.

Loop state and events are durable:

```text
.blackhole-agent/unbound/
  continuous-loop.json
  continuous-loop-events.jsonl
  continuous-loop.lock
```

Inspect the scheduler or request a cooperative stop:

```bash
uv run blackhole-unbound loop-status --repo-path .
uv run blackhole-unbound loop-stop --repo-path .
```

The stop request wakes a sleeping loop immediately. If a mission is currently
running, the loop stops after that mission returns.
