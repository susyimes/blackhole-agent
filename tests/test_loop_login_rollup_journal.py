import json
import os
from pathlib import Path

import pytest

from blackhole_agent.loop_login_audit import login_audit_log_path
from blackhole_agent.loop_login_compact import compact_login_audit_tombstones
from blackhole_agent.loop_login_rollup import LOGIN_AUDIT_ROLLUP_EVENT
from blackhole_agent.loop_login_rollup_journal import (
    LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT,
    login_rollup_repair_journal_path,
    read_login_rollup_repair_journal,
)
from blackhole_agent.loop_login_rollup_repair import repair_login_audit_rollup
from blackhole_agent.loop_login_verify import verify_login_audit_rollup


def seed(root: Path, **overrides) -> dict:
    record = {
        "schema_version": 1, "event": LOGIN_AUDIT_ROLLUP_EVENT, "rollup": True,
        "compacted_count": 0, "compaction_runs": 3,
        "oldest_pruned_at": "2020-01-01T00:00:00Z", "newest_pruned_at": "2020-03-01T00:00:00Z",
        "last_compacted_at": "2021-01-01T00:00:00Z", **overrides,
    }
    login_audit_log_path(root).write_text(json.dumps(record) + "\n", encoding="utf-8")
    return record


def test_duplicate_claims_and_history_survive_later_compaction(tmp_path: Path):
    prior = seed(tmp_path, operator_note={"unicode": "旧声明", "claims": [0, None, False]})
    extra = dict(prior, compacted_count=10, compaction_runs=2, operator_note="second record")
    path = login_audit_log_path(tmp_path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(extra) + "\n")
    repaired = repair_login_audit_rollup(tmp_path)
    entries = read_login_rollup_repair_journal(tmp_path)["entries"]
    assert repaired["repaired"] and repaired["repair_journal_completed"]
    assert entries[0]["prior_rollups"] == [prior, extra]
    assert entries[0]["corrected_rollup"] == repaired["rollup"]
    assert entries[0]["state"] == "applied"
    assert entries[0]["repair_id"] == repaired["rollup"]["repair_id"]
    journal_bytes = login_rollup_repair_journal_path(tmp_path).read_bytes()
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT

    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "event": LOGIN_AUDIT_TOMBSTONE_EVENT, "tombstone": True,
            "task_name": "another-old-record", "pruned_at": "2022-01-01T00:00:00Z",
        }) + "\n")
    assert compact_login_audit_tombstones(tmp_path)["compacted"]
    assert verify_login_audit_rollup(tmp_path)["verified"]
    assert login_rollup_repair_journal_path(tmp_path).read_bytes() == journal_bytes
    assert read_login_rollup_repair_journal(tmp_path)["entries"] == entries


def test_journal_failure_prevents_replacement_and_retry_retains_claims(tmp_path: Path):
    original = seed(tmp_path)
    path = login_audit_log_path(tmp_path)
    before = path.read_bytes()
    journal = login_rollup_repair_journal_path(tmp_path)
    journal.mkdir()
    report = repair_login_audit_rollup(tmp_path)
    assert report["reason"] == "journal_write_failed"
    assert not report["repaired"] and not report["repair_journaled"]
    assert report["journal_path"] == str(journal) and report["error"]
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    journal.rmdir()
    assert repair_login_audit_rollup(tmp_path)["repaired"]
    assert read_login_rollup_repair_journal(tmp_path)["entries"][0]["prior_rollups"] == [original]


def test_receipt_is_synced_before_replacement(tmp_path: Path, monkeypatch):
    original = seed(tmp_path)
    journal = login_rollup_repair_journal_path(tmp_path)
    actual_sync, actual_replace = os.fsync, os.replace
    synced_journal = False

    def sync(fd):
        nonlocal synced_journal
        actual_sync(fd)
        if journal.exists() and os.fstat(fd).st_ino == journal.stat().st_ino:
            synced_journal = True

    def replace(source, destination):
        assert synced_journal
        raw = [json.loads(line) for line in journal.read_bytes().splitlines()]
        assert len(raw) == 1 and raw[0]["state"] == "prepared"
        assert raw[0]["prior_rollups"] == [original]
        assert json.loads(Path(destination).read_text(encoding="utf-8")) == original
        actual_replace(source, destination)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "replace", replace)
    assert repair_login_audit_rollup(tmp_path)["repaired"]


@pytest.mark.parametrize("failed_sync", ["trail", "journal"])
def test_sync_failure_keeps_original_trail(tmp_path: Path, monkeypatch, failed_sync: str):
    seed(tmp_path)
    path = login_audit_log_path(tmp_path)
    before = path.read_bytes()
    journal = login_rollup_repair_journal_path(tmp_path)
    actual_sync = os.fsync

    def fail_sync(fd):
        is_journal = journal.exists() and os.fstat(fd).st_ino == journal.stat().st_ino
        if is_journal == (failed_sync == "journal"):
            raise OSError("injected sync failure")
        actual_sync(fd)

    monkeypatch.setattr(os, "fsync", fail_sync)
    report = repair_login_audit_rollup(tmp_path)
    assert not report["repaired"]
    assert report["reason"] == ("journal_write_failed" if failed_sync == "journal" else "audit_write_failed")
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_replacement_remains_prepared_and_retry_is_a_separate_attempt(tmp_path: Path, monkeypatch):
    prior = seed(tmp_path)
    path = login_audit_log_path(tmp_path)
    before = path.read_bytes()

    def fail_replace(*args):
        raise OSError("replacement denied")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_replace)
        report = repair_login_audit_rollup(tmp_path)
    assert report["repair_journaled"] and not report["repaired"]
    assert report["reason"] == "audit_write_failed"
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    journal = read_login_rollup_repair_journal(tmp_path)
    assert journal["entries"][0]["state"] == "prepared"
    assert journal["entries"][0]["prior_rollups"] == [prior]
    retried = repair_login_audit_rollup(tmp_path)
    entries = read_login_rollup_repair_journal(tmp_path)["entries"]
    assert retried["repaired"] and len(entries) == 2
    assert [entry["state"] for entry in entries] == ["prepared", "applied"]
    assert entries[0]["repair_id"] != entries[1]["repair_id"]
    assert entries[1]["prior_rollups"] == [prior]


def test_failed_completion_keeps_receipt_and_readback_confirms_applied_rollup(tmp_path: Path, monkeypatch):
    from blackhole_agent import loop_login_rollup_journal as journal_module

    prior = seed(tmp_path)

    def fail_complete(*args):
        return {"journaled": False, "error": "completion unavailable"}

    monkeypatch.setattr(journal_module, "complete_login_rollup_repair", fail_complete)
    repaired = repair_login_audit_rollup(tmp_path)
    assert repaired["repaired"] and repaired["repair_journaled"]
    assert not repaired["repair_journal_completed"] and repaired["journal_completion_error"]
    path = login_rollup_repair_journal_path(tmp_path)
    raw = path.read_bytes()
    assert json.loads(raw)["state"] == "prepared"
    entry = read_login_rollup_repair_journal(tmp_path)["entries"][0]
    assert entry["state"] == "applied"
    assert entry["completion_evidence"] == "matching_rollup_in_trail"
    assert entry["prior_rollups"] == [prior]
    assert entry["corrected_rollup"] == repaired["rollup"]
    assert path.read_bytes() == raw


@pytest.mark.parametrize("tail", [b'{"broken":', b'\xff\xfe', b'{"unrelated": true}'])
def test_torn_journal_tail_cannot_swallow_new_receipt(tmp_path: Path, tail: bytes):
    prior = seed(tmp_path)
    path = login_rollup_repair_journal_path(tmp_path)
    path.write_bytes(tail)
    repaired = repair_login_audit_rollup(tmp_path)
    history = read_login_rollup_repair_journal(tmp_path)
    assert repaired["repaired"] and repaired["repair_journal_completed"]
    assert history["entry_count"] == 1 and history["malformed_count"] == 1
    assert history["entries"][0]["prior_rollups"] == [prior]
    assert path.read_bytes().startswith(tail + b"\n")


@pytest.mark.parametrize("contents", [None, "", "{}\n", '{"broken":', json.dumps({
    "event": LOGIN_AUDIT_ROLLUP_EVENT, "rollup": True, "compacted_count": 0,
})])
def test_missing_empty_malformed_and_unrepairable_trails_journal_nothing(tmp_path: Path, contents):
    path = login_audit_log_path(tmp_path)
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    before = path.read_bytes() if path.exists() else None
    report = repair_login_audit_rollup(tmp_path)
    assert not report["repaired"] and not report["repair_journaled"]
    assert (path.read_bytes() if path.exists() else None) == before
    assert not login_rollup_repair_journal_path(tmp_path).exists()


def test_journal_read_reports_io_errors_and_handles_incomplete_receipt(tmp_path: Path):
    path = login_rollup_repair_journal_path(tmp_path)
    path.mkdir()
    assert read_login_rollup_repair_journal(tmp_path)["reason"] == "journal_read_failed"
    path.rmdir()
    path.write_text(json.dumps({
        "event": LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT, "journal": True,
        "state": "prepared", "repair_id": "incomplete",
    }) + "\n", encoding="utf-8")
    seed(tmp_path)
    assert read_login_rollup_repair_journal(tmp_path)["entries"][0]["state"] == "prepared"
