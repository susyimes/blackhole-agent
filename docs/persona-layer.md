# Persona Layer

The persona layer is the agent's durable self-model. It is inspired by a Hermes-like pattern: the agent is a messenger between public ecosystem signals and local self-improvement, but it must remain bounded, inspectable, and restartable only through an external supervisor.

The executable source of truth lives in `blackhole_agent.persona`.

## Purpose

The layer keeps the core mechanism in one place:

- track public GitHub trends on a scheduled cadence
- digest noisy activity into evidence and proposals
- choose one safe, testable improvement
- modify only the local checkout through the Codex CLI kernel
- create a rollback point before any local self-modification
- verify the change locally
- leave reviewable artifacts
- require approval before external writes
- let an external scheduler or supervisor handle restart

## Why It Exists

Without this layer, self-evolution instructions would be scattered across README text, controller code, and generated prompts. The persona layer makes those instructions versioned and testable.

## Restart Boundary

The agent may prepare code that supports restart, but it does not restart itself inside the local Codex kernel. A future restart path should:

- require a rollback point from the run being activated
- persist digest state and run metadata
- verify the candidate branch or commit
- hand off to an external scheduler or supervisor
- resume from durable state after restart

This keeps self-improvement separate from activation.

## Universal Rollback

Every self-evolution run that may modify source code should first create a rollback point. The rollback point records:

- original branch
- original HEAD
- local rollback ref
- pre-run dirty status
- recovery commands

The controller writes `latest-rollback-point.json` and `latest-rollback-point.md` into the run output directory before switching to the self-evolution branch.

The recovery commands are intentionally explicit and destructive:

```bash
git switch <original-branch>
git reset --hard <rollback-ref>
git clean -fd
```

This is the escape hatch for failed startup, broken imports, bad migrations, or unsafe behavior after activation. The agent may prepare and document rollback, but a human operator or external supervisor must choose when to execute it.
