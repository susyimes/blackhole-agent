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
uv run blackhole-unbound capability scout
uv run blackhole-unbound capability absorb domain.local-memory
uv run blackhole-unbound capability promote repo.import-health,capability.ledger-inventory,unbound.milestone-gate
uv run blackhole-unbound capability grow
```

Each capability has an `entry` (command or `module:function`), a
`proof_command`, optional dependencies, and behavior-path provenance. Turn
prompts inject a compact ledger summary so later turns can compound rather than
re-derive the same ability. Milestone acceptance best-effort registers a
capability when a successful validation command is present.

### Growth loop (scout → absorb/promote → prove)

The compounder can grow beyond bootstrap seeds without skill-route discovery:

- `capability scout` ranks ready multi-capability recipes, absorbable domain
  package surfaces (memory, tool routing, harness activation), and unproved ids.
- `capability absorb` registers a catalogued domain module surface as a durable
  invocable capability (filesystem-present, not skill-route derived).
- `capability promote` materializes a member set as one durable python capability
  whose entry re-composes its dependencies (`BLACKHOLE_CAPABILITY_ID`).
- `capability grow` runs the closed loop once: scout a ready composition or
  domain surface, absorb/promote it, prove and run the new capability, and
  persist the larger ledger.

When meta health compositions are exhausted, growth continues by absorbing
domain surfaces and promoting multi-domain compositions (e.g.
`capability.composed-domain-core`, then operational surfaces such as
`domain.issue-triage`, `domain.ci-security`, `domain.proposal-eval` and
`capability.composed-domain-ops`).

After catalogued recipes and domain absorbs are promoted, scout synthesizes
**dynamic multi-domain compositions** from absorbed domain leaves so growth
does not plateau on re-prove-only. Multiple deterministic frontiers are ranked;
promoting one dynamic unit does not exhaust the scout. Synthesized capabilities
are tagged `dynamic` in addition to `composed`/`promoted`.

When leaf and dynamic frontiers still leave room, scout promotes **hierarchical
stacks**: compositions of already-promoted compositions (catalog pillars such as
`capability.composed-stack-platform`, plus synthesized pillar pairs). These are
tagged `hierarchical` and keep `capability grow` expanding past the domain-ops
re-prove plateau without skill-route machinery.

When first-order hierarchical stacks still leave room, scout promotes
**meta-hierarchical** stack-of-stacks (tagged `meta`), then **third-order
superstacks** pairing meta units (`capability.composed-super-*`, tagged
`superstack`) so growth does not die on re-prove after meta recipes exhaust.

Operators can also:

```bash
uv run blackhole-unbound capability grow --budget 8
uv run blackhole-unbound capability integrity
uv run blackhole-unbound capability integrity --limit 16
```

- `capability grow --budget N` runs adaptive multi-step growth until the budget
  is exhausted or no ready frontier remains (domain absorb, dynamic, hierarchical,
  meta, superstack). Scout ranks **novel primitive coverage** ahead of combinatorial
  superstacks that re-package the same leaves.
- `capability integrity` batch-proves the ledger DAG in topological order and
  reports an integrity score (`capability.ledger-integrity`).
- `capability novelty` ranks ready frontiers by primitive-coverage novelty
  (`capability.frontier-novelty`).
- `capability distill` collapses redundant identical-coverage stacks (soft-tag or
  `--remove`; `capability.distill-ledger`).
- `capability autonomic` runs novelty-aware grow → distill → integrity as one
  invocable cycle (`capability.autonomic-cycle`).
- `capability second-wave` absorbs ready second-wave domain primitives (persona,
  proposal synthesis, kernel preflight, …) to expand coverage when superstacks
  plateau (`capability.second-wave-absorb`).
- `capability plan` / `capability program` compile and run multi-step capability
  programs from free-text goals (`capability.goal-plan`, `capability.program-run`).
- `capability mission-plane` is the closed mission plane: second-wave absorb →
  goal plan → program run → novel-only grow (`capability.mission-plane`).
- `capability contract` machine-checks a structured or free-text `done_when`
  against live ledger metrics, proof status, and optional programs
  (`capability.outcome-contract`). Predicate forms include
  `min_capabilities:N`, `min_primitives:N`, `capability_exists:id`,
  `capability_proved:id`, `program_passes:id1,id2`, `no_skill_route`,
  `mission_plane_ok`, and more.
- `capability contract-plane` is the evidence plane: mission plane then
  outcome-contract evaluation so completion is ledger/program-backed
  (`capability.contract-plane`). Unbound milestone gating also refuses
  `complete` when `done_when` is machine-checkable and predicates fail.

Promoted compositions are tagged `composed`/`promoted` and become ordinary
ledger citizens that later turns can list, prove, run, and compose further.

### Evolution surface redirect

When the ledger is ready (≥2 capabilities), growth prefers the compounder:

- Supervisor wakes with `evolution_mode=compound`, or `codex` with
  `--prefer-capability-compounder` (default), launch
  `blackhole-unbound capability demo` instead of the github_growth skill-route
  mutation path.
- Digest attachment of `skill_route_discovery_capability_pipeline` short-circuits
  to a compact `capability_compounder_redirect` surface that freezes pin/cascade
  packaging and sets `supervisor_next_action=run_capability_compounder_compose_or_demo`.
- Force the legacy pipeline with `BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE=1` or
  `--prefer-legacy-growth`.

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

After a mission reaches `complete`, the CLI defaults to publishing the exact
proven lineage commit to `origin/main` with a normal non-force push. The remote
ref is read before the push and verified afterward. A rejected or unavailable
push leaves `pending_publish_ref` in loop state, waits 30 minutes, and retries;
the controller does not create the next mission until publication succeeds.

Use another configured remote with `--publish-remote <name>`. Pass an empty
value only when a deliberately local-only loop is wanted.

Loop state and events are durable:

```text
.blackhole-agent/unbound/
  continuous-loop.json
  continuous-loop-events.jsonl
  continuous-loop.lock
```

`continuous-loop.json` records `publish_attempt_count`, `publish_count`,
`pending_publish_ref`, `last_published_ref`, and `last_publish_error` so remote
delivery is observable independently from local milestone creation.

Inspect the scheduler or request a cooperative stop:

```bash
uv run blackhole-unbound loop-status --repo-path .
uv run blackhole-unbound loop-stop --repo-path .
```

The stop request wakes a sleeping loop immediately. If a mission is currently
running, the loop stops after that mission returns.
