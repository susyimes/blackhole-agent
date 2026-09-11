# Continuous loop recovery

`loop-status` now adds a read-only `pid_alive`, `effective_status`, `checked_at`
and `liveness_error` to the durable state. An active-looking state with no owner
process is reported as `effective_status=orphaned`; the command does not rewrite
the evidence on disk. A live PID alone is not health proof: verify its command
line, creation time and mission/Cursor descendant tree as well.

Before creating a new mission the loop records `creating_mission`, a start time,
the checkout timeout and a `continuous_loop.mission_creating` event. A machine
restart during checkout can leave an initializing worktree without a mission
state. Preserve that worktree and branch; do not reset/remove it or treat staged
deletions caused by a missing index as an agent's completed work.

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
