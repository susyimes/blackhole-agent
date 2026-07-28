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

## Capability Compounder

Accepted milestones can become durable, invocable capabilities stored in
`capabilities/ledger.json`. The ledger is independent of the legacy
`skill_route_discovery` pipeline. Operators and the Unbound agent can:

```bash
uv run blackhole-unbound capability seed
uv run blackhole-unbound capability list
uv run blackhole-unbound capability prove repo.import-health
uv run blackhole-unbound capability compose repo.import-health,unbound.milestone-gate,capability.ledger-inventory
uv run blackhole-unbound capability demo
```

Each capability has an `entry` (command or `module:function`), a
`proof_command`, optional dependencies, and behavior-path provenance. Turn
prompts inject a compact ledger summary so later turns can compound rather than
re-derive the same ability. Milestone acceptance best-effort registers a
capability when a successful validation command is present.

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
