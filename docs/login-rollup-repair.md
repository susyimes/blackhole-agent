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

Each successful receipt or completion append also prunes completed repairs
older than **365 days**. Age is measured from the latest receipt or completion
timestamp, not from the dates inside the drifted claims. The exact cutoff
day is retained. A receipt and its completion markers expire together, so
completion markers cannot accumulate on their own. Legacy applied receipts
without a state or repair ID also expire.

Recent repairs, unresolved `prepared` attempts, ambiguous duplicate IDs,
unknown schemas, invalid or missing dates, unrelated records, and malformed
bytes are preserved. This bounds normal repair history by age; unresolved or
uninterpretable evidence requires operator investigation and is not subject
to a hard size cap. Retained lines remain byte-identical. Readback stays
read-only, and trail compaction does not modify the journal.

For an idle journal, or a custom retention window of at least one day:

```powershell
uv run blackhole-unbound loop-login-journal-prune --repo-path C:\repo --output-dir C:\repo\login-state --retention-days 365
```

The prune report includes `pruned_count` (receipts), `pruned_marker_count`,
`kept_count`, and `reason`. Repair exposes the append's maintenance reports
as `journal_prune` and `journal_completion_prune`. A maintenance write failure
reports `journal_write_failed` without invalidating a receipt already synced
or a repair already applied. Retry pruning after storage recovers.

Pruning syncs a temporary file before atomic replacement. Appends and pruning
share the dedicated `login-rollup-repair-journal.jsonl.guard` OS lock; this
constant-size file must remain in place to serialize writers. A process exit
releases the OS lock automatically; contention waits up to five seconds and
then reports a failure for retry. No PID lock is acquired or changed.

Already verified, missing, malformed, or unrepairable trails add no receipt.
Repair and retention touch only the selected audit trail, journal, and journal
guard; they do not change owner state, owner locks, registrations, launchers,
or scheduled tasks, and never follow repo paths recorded in old claims.
