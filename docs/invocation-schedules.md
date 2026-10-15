# Interval schedules

Start the capability service with `--schedule` to enable persisted interval
jobs. Every server using the same local `--root` shares the same schedules.

```sh
python -m blackhole_agent.capability_service serve --root /path/to/repo --port 8765 --schedule
```

Create a schedule using the same capability id and input as `POST /invoke`:

```http
POST /schedules
Content-Type: application/json

{"capability_id":"capability.absorbed-text-reverser","input":{"raw_text":"hello"},"every_seconds":60}
```

The response is HTTP 201 with `schedule_id`. The first fire is due immediately.
`GET /schedules/{schedule_id}` reports the last status, output, invocation id,
and completed attempt count. `DELETE /schedules/{schedule_id}` stops future
fires; a fire already reserved may finish. Creation and deletion require the
operator identity when authentication is configured.

Only one process owns the scheduler for a root. Other processes continue to
serve HTTP, including schedule creation and deletion, while waiting for the
owner's OS lock. `GET /health` exposes `scheduler_role` as `owner`, `standby`,
or `disabled`. A slow tool cannot overlap another fire of its own schedule.
Different schedules can execute concurrently within the invocation limits.

A graceful stop retains ownership until its active tools finish. A standby
then acquires ownership and continues completed or pending schedules from
their persisted deadlines. Missed deadlines are coalesced into one next fire;
the scheduler does not replay a backlog.

If the owner dies during a reserved fire, its effects may already have
happened. The successor marks that schedule `interrupted`, sets `last_error`
to `schedule_outcome_unknown` with reconciliation instructions, and leaves it
paused. Inspect the tool's external effects and any available invocation
artifacts, then deliberately delete and recreate the schedule if it should
run again. Other schedules continue normally. This is not an exactly-once
guarantee for arbitrary tool side effects.

The guard file `.blackhole-agent/invocation-schedules.guard` is permanent.
Its existence does not indicate ownership: the OS lock does. Do not remove it
while services are running, since that could create competing lock files.
