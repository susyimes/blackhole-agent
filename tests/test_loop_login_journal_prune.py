import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_journal_prune import prune_login_rollup_repair_journal
from blackhole_agent.loop_login_rollup import LOGIN_AUDIT_ROLLUP_EVENT
from blackhole_agent.loop_login_rollup_journal import (
    LOGIN_ROLLUP_REPAIR_APPLIED_EVENT,
    LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT,
    login_rollup_repair_journal_path,
    read_login_rollup_repair_journal,
    record_login_rollup_repair,
    repair_journal_guard,
)

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=366)).isoformat()


def receipt(repair_id="old", **overrides):
    return {
        "event": LOGIN_ROLLUP_REPAIR_JOURNAL_EVENT, "schema_version": 1,
        "journal": True, "repair_id": repair_id, "state": "prepared",
        "journaled_at": OLD, "repaired_at": OLD,
        "prior_rollups": [{"claim": "keep this exactly"}], "corrected_rollup": {"claim": "corrected"},
        **overrides,
    }


def marker(repair_id="old", **overrides):
    return {"event": LOGIN_ROLLUP_REPAIR_APPLIED_EVENT, "schema_version": 1,
            "repair_id": repair_id, "applied_at": OLD, **overrides}


def line(record):
    return (json.dumps(record) + "\r\n").encode()


def seed(root, *records):
    path = login_rollup_repair_journal_path(root)
    path.write_bytes(b"".join(line(record) if isinstance(record, dict) else record for record in records))
    return path


def test_prune_pairs_legacy_and_raw_survivors_without_touching_claim_paths(tmp_path):
    foreign = tmp_path / "live-owner.json"
    foreign.write_bytes(b'{"pid":123,"status":"running"}')
    stale = receipt(repo_path=str(tmp_path), prior_rollups=[{"path": str(foreign)}])
    legacy = receipt(state="applied")
    legacy.pop("repair_id")
    legacy.pop("state")
    kept = line(receipt("pending")) + b'\r\n{ "alien": true }\r\n\xff\xfe\r\n{"torn":'
    path = seed(tmp_path, stale, marker(), legacy, kept)
    report = prune_login_rollup_repair_journal(tmp_path, now=NOW)
    assert report["pruned"] and report["pruned_count"] == 2 and report["pruned_marker_count"] == 1
    assert report["kept_count"] == 1 and path.read_bytes() == kept
    assert foreign.read_bytes() == b'{"pid":123,"status":"running"}'
    assert not list(tmp_path.glob("*.tmp"))
    stat = path.stat()
    assert prune_login_rollup_repair_journal(tmp_path, now=NOW)["reason"] == "nothing_stale"
    assert path.read_bytes() == kept and path.stat().st_mtime_ns == stat.st_mtime_ns


@pytest.mark.parametrize("age,expired", [(364, False), (365, False), (366, True)])
@pytest.mark.parametrize("offset", [timezone.utc, timezone(timedelta(hours=8))])
def test_cutoff_and_offsets(tmp_path, age, expired, offset):
    stamp = (NOW - timedelta(days=age)).astimezone(offset).isoformat()
    path = seed(tmp_path, receipt(journaled_at=stamp, repaired_at=stamp), marker(applied_at=stamp))
    before = path.read_bytes()
    result = prune_login_rollup_repair_journal(tmp_path, now=NOW)
    assert result["pruned"] is expired
    assert path.read_bytes() == (b"" if expired else before)


@pytest.mark.parametrize("changes", [
    {"journaled_at": "invalid"}, {"repaired_at": ""}, {"journaled_at": None}, {"journaled_at": 20200101},
    {"journaled_at": "9999-12-31T23:59:59-23:59"}, {"state": []}, {"state": "future-state"},
    {"schema_version": 2}, {"schema_version": True}, {"repair_id": ["invalid"]},
    {"repair_id": [], "state": "applied"},
    {"journaled_at": NOW.isoformat()}, {"applied_at": NOW.isoformat()},
    {"journaled_at": (NOW + timedelta(days=100)).isoformat()},
])
def test_uncertain_or_recent_receipts_are_kept(tmp_path, changes):
    path = seed(tmp_path, receipt(**changes), marker())
    before = path.read_bytes()
    assert not prune_login_rollup_repair_journal(tmp_path, now=NOW)["pruned"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("completion", [
    marker(applied_at="invalid"), marker(applied_at=NOW.isoformat()), marker(schema_version=2),
    {"event": LOGIN_ROLLUP_REPAIR_APPLIED_EVENT, "repair_id": "old"},
])
def test_marker_must_also_have_aged_out(tmp_path, completion):
    path = seed(tmp_path, receipt(), completion)
    before = path.read_bytes()
    assert not prune_login_rollup_repair_journal(tmp_path, now=NOW)["pruned"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("records", [
    [receipt()], [marker()], [marker(), receipt()], [receipt(), receipt(), marker()],
    [receipt(state="applied", journaled_at=None, repaired_at=None)],
])
def test_unresolved_or_ambiguous_groups_are_kept(tmp_path, records):
    path = seed(tmp_path, *records)
    before = path.read_bytes()
    assert not prune_login_rollup_repair_journal(tmp_path, now=NOW)["pruned"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("retention", [0, -1, True, 1.5, "365", 10**30])
def test_invalid_retention_cannot_delete(tmp_path, retention):
    path = seed(tmp_path, receipt(), marker())
    before = path.read_bytes()
    assert prune_login_rollup_repair_journal(tmp_path, retention_days=retention)["reason"] == "invalid_retention_days"
    assert path.read_bytes() == before


def test_missing_log_and_unreadable_log(tmp_path):
    missing = tmp_path / "absent"
    assert prune_login_rollup_repair_journal(missing)["reason"] == "no_journal"
    assert not missing.exists()
    login_rollup_repair_journal_path(tmp_path).mkdir()
    assert prune_login_rollup_repair_journal(tmp_path)["reason"] == "journal_read_failed"


@pytest.mark.parametrize("failure", ["fsync", "replace", "mkstemp"])
def test_atomic_write_failure_preserves_entire_log_and_cleans_temp(tmp_path, monkeypatch, failure):
    from blackhole_agent import loop_login_journal_prune as prune_module

    path = seed(tmp_path, receipt(), marker())
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk unavailable")

    target = prune_module.tempfile if failure == "mkstemp" else prune_module.os
    monkeypatch.setattr(target, failure, fail)
    result = prune_login_rollup_repair_journal(tmp_path, now=NOW)
    assert not result["pruned"] and result["pruned_count"] == 0 and result["kept_count"] == 1
    assert result["reason"] == "journal_write_failed" and path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_automatic_prune_failure_does_not_invalidate_synced_repair(tmp_path, monkeypatch):
    from blackhole_agent.loop_login_audit import login_audit_log_path
    from blackhole_agent.loop_login_rollup_repair import repair_login_audit_rollup

    path = seed(tmp_path, receipt(), marker())
    # Use genuinely old dates so automatic retention runs at wall clock time.
    path.write_bytes(path.read_bytes().replace(OLD.encode(), b"2000-01-01T00:00:00Z"))
    old_bytes = path.read_bytes()
    audit = login_audit_log_path(tmp_path)
    original = {"event": LOGIN_AUDIT_ROLLUP_EVENT, "rollup": True, "compacted_count": 0,
                "compaction_runs": 3, "oldest_pruned_at": OLD, "newest_pruned_at": OLD}
    audit.write_bytes(line(original))
    replace = os.replace

    def fail_journal_replace(source, destination):
        if Path(destination) == path:
            raise OSError("retention write unavailable")
        replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_journal_replace)
    result = repair_login_audit_rollup(tmp_path)
    assert result["repaired"] and result["repair_journal_completed"]
    assert result["journal_prune"]["reason"] == "journal_write_failed"
    assert result["journal_completion_prune"]["reason"] == "journal_write_failed"
    assert path.read_bytes().startswith(old_bytes)
    assert read_login_rollup_repair_journal(tmp_path)["entries"][-1]["prior_rollups"] == [original]
    assert not list(tmp_path.glob("*.tmp"))


def test_new_journaled_time_protects_backdated_repair(tmp_path):
    result = record_login_rollup_repair(tmp_path, drift=[], corrections=[], prior_rollup={},
                                      corrected_rollup={}, repaired_at="1900-01-01T00:00:00Z")
    assert result["journaled"] and not result["journal_prune"]["pruned"]
    assert read_login_rollup_repair_journal(tmp_path)["entry_count"] == 1


def test_cli_custom_retention_and_idle_log(tmp_path):
    stamp = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    path = seed(tmp_path, receipt(journaled_at=stamp, repaired_at=stamp), marker(applied_at=stamp))
    runner = CliRunner()
    args = ["loop-login-journal-prune", "--repo-path", str(tmp_path), "--output-dir", str(tmp_path)]
    normal = runner.invoke(unbound.app, args)
    assert normal.exit_code == 0 and not json.loads(normal.stdout)["pruned"]
    custom = runner.invoke(unbound.app, args + ["--retention-days", "30"])
    assert custom.exit_code == 0 and json.loads(custom.stdout)["pruned_count"] == 1
    assert path.read_bytes() == b""
    assert runner.invoke(unbound.app, args + ["--retention-days", "0"]).exit_code != 0


def test_waiting_append_cannot_be_lost_by_prune_replacement(tmp_path):
    import blackhole_agent

    path = seed(tmp_path, receipt(), marker())
    ready = tmp_path / "writer-ready"
    source = str(Path(blackhole_agent.__file__).resolve().parent.parent)
    script = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from blackhole_agent.loop_login_rollup_journal import record_login_rollup_repair
Path(sys.argv[3]).write_text('ready')
print(json.dumps(record_login_rollup_repair(Path(sys.argv[2]), drift=[], corrections=[],
    prior_rollup={'claim': 'concurrent'}, corrected_rollup={}, repaired_at='2000-01-01T00:00:00Z')))
"""
    process = None
    try:
        with repair_journal_guard(path):
            process = subprocess.Popen([sys.executable, "-I", "-c", script, source, str(tmp_path), str(ready)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            import time

            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists() and process.poll() is None
            # Exercise the same locked rewrite while the real writer waits.
            from blackhole_agent.loop_login_journal_prune import _prune_locked

            report = _prune_locked(path, {}, NOW, timedelta(days=365))
            assert report["pruned"] and path.read_bytes() == b""
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["journaled"]
        assert read_login_rollup_repair_journal(tmp_path)["entries"][0]["prior_rollup"] == {"claim": "concurrent"}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
