# Auditing a login rollup repair

Use the same login state root for repair and history readback:

```powershell
uv run blackhole-unbound loop-login-rollup-repair --repo-path C:\repo --output-dir C:\repo\login-state
uv run blackhole-unbound loop-login-rollup-journal --repo-path C:\repo --output-dir C:\repo\login-state
```

`login-rollup-repair-journal.jsonl` sits beside `login-scrub-audit.jsonl`.
Each repair receipt preserves `prior_rollups` in original trail order,
including every duplicate and its extra fields. `prior_rollup` continues
to expose the first record. `corrected_rollup`, `drift`, and `corrections`
show the proposed replacement and why it changed. The receipt and corrected
rollup share a `repair_id`.

Repair verifies the proposed trail, writes and syncs its temporary file,
then appends, flushes, and syncs the complete receipt **before** replacing
the trail. If writing the receipt fails, repair returns
`repaired: false`, `reason: journal_write_failed`, and leaves the drifted
trail unchanged. After storage recovers, rerun the repair command.

Receipts start with `state: prepared`. A small completion record follows
successful replacement; the journal read command combines the two into
one history entry with `state: applied`. If a process stops after replacing
the trail but before recording completion, readback can confirm the exact
replacement still present in the trail and reports
`completion_evidence: matching_rollup_in_trail`. Otherwise the attempt
remains `prepared`; its correction is a proposal, not proof of application.
`repaired_at` in a prepared receipt is the proposed correction time.

If the completion append fails, the repair result reports
`repair_journal_completed: false` and `journal_completion_error`; the
synced receipt still contains all old claims and the replacement.
Readback does not modify files. Torn or invalid journal lines are counted
in `malformed_count`; appending a later repair preserves the torn bytes
and starts a new line. Unreadable journals report `journal_read_failed`.

Repeated repairs append history. Later trail compaction leaves that history
intact. Already verified, missing, malformed, or unrepairable trails add no
receipt. Repair touches the selected audit trail and journal; it does not
change owner state, owner locks, registrations, launchers, or scheduled tasks.
