# Continuous loop recovery

`loop-status` checks owner liveness and reaps a confirmed dead controller. It
persists `status=orphaned`, the previous status, reaping time and reason, removes
the stale PID lock, and appends one `continuous_loop.orphaned` event. Repeated
checks leave the receipt unchanged. Mission state, worktrees, lineage references,
pending publication and existing error diagnostics remain available for recovery.
`loop-stop` also reaps a dead controller instead of waiting for it to consume a
stop request. Neither command terminates processes or resumes a mission.

Use `loop-status --read-only` for inspection without changing state or locks.
Both modes add `pid_alive`, `effective_status`, `checked_at` and `liveness_error`.
A malformed PID or failed process query produces unknown liveness, not evidence
of death. A live PID alone is not health proof: verify its command line, creation
time and mission/Cursor descendant tree as well; PID reuse is treated conservatively.

Controllers and reapers share an OS ownership guard, released automatically when
the owner process exits. The `.lock.guard` file stays on disk as the stable lock
target; its existence does not indicate an active controller. Reaping rechecks
the state and PID lock while holding this guard and refuses live or uncertain
owners. An unknown PID lock must be investigated before recovery. There is no
background watcher: reconciliation happens when status or stop is invoked.

Before creating a new mission the loop records `creating_mission`, a start time,
the checkout timeout and a `continuous_loop.mission_creating` event. A machine
restart during checkout can leave an initializing worktree without a mission
state. Preserve that worktree and branch; do not reset/remove it or treat staged
deletions caused by a missing index as an agent's completed work. At startup the
loop reconciles such stateless leftovers before the next creation: every
worktree-parent directory without a `missions/<id>/state.json` is named, with
its branch and head, in the durable `orphaned-creations.json` inventory and in
one `continuous_loop.mission_create_interrupted` event. Reconciliation is
idempotent, touches nothing with mission state, and never deletes the preserved
worktree or branch.

Controller commands use file-backed output capture. This avoids Windows
`subprocess.run(..., capture_output=True)` waiting indefinitely for pipe EOF
after killing a timed-out Git wrapper whose child still holds the pipe. A timeout
terminates only the invocation's process tree and returns the captured diagnostics
within the timeout plus a bounded cleanup grace (at most 15 seconds). Existing
worktree creation failure handling then records the error and waits the configured
900 seconds before retrying. No repository files or locks are deleted by this
timeout handler.

On 2026-09-11 the missing Cursor loop was found after Windows servicing reboots
at 2026-09-10 21:33-21:34 +08. Its last durable update was 19:16, during a checkout
that remained `locked initializing`; no exception/exit receipt established why
checkout stopped advancing before the reboot. The published `d0666b97` mission
was retained. The timeout repair addresses the demonstrated inherited-pipe failure
mode, not a proven claim that it was the only cause of that historical checkout.

A background process is not a Windows startup service. Login/reboot restoration
requires a separately enabled startup mechanism. Do not silently re-enable a
paused daily health automation when restoring the native loop.
