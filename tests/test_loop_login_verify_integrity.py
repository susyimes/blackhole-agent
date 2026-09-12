"""Uninterpretable audit evidence must never become successful verification."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackhole_agent import unbound
from blackhole_agent.loop_login_audit import login_audit_log_path, read_login_scrub_audit
from blackhole_agent.loop_login_rollup import LOGIN_AUDIT_ROLLUP_EVENT
from blackhole_agent.loop_login_rollup_repair import repair_login_audit_rollup
from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
from blackhole_agent.loop_login_verify import verify_login_audit_rollup, verify_login_audit_rollup_records


def rollup(**changes):
    return dict({
        "schema_version": 1,
        "event": LOGIN_AUDIT_ROLLUP_EVENT,
        "rollup": True,
        "compacted_count": 2,
        "compaction_runs": 1,
        "oldest_pruned_at": "2024-01-01T00:00:00Z",
        "newest_pruned_at": "2024-02-01T00:00:00Z",
    }, **changes)


@pytest.mark.parametrize("bad_line", [
    '{"event":"login_audit_tombstones_compacted",',
    '{"event":"login_audit_record_pruned",',
    '[]',
    'null',
    '{"x": NaN}',
    '{"x": Infinity}',
    '{"compacted_count":0,' + json.dumps(rollup())[1:],
])
def test_malformed_evidence_blocks_verification_and_repair(tmp_path, bad_line):
    path = login_audit_log_path(tmp_path)
    raw = (json.dumps(rollup(compacted_count=0)) + "\n\n" + bad_line + "\n").encode()
    path.write_bytes(raw)
    verified = verify_login_audit_rollup(tmp_path)
    audit = read_login_scrub_audit(tmp_path)
    repair = repair_login_audit_rollup(tmp_path)
    assert verified["verified"] is False
    assert "trail_malformed" in verified["drift"]
    assert verified["malformed_lines"] == [3]
    assert audit["entry_count"] == 1
    assert audit["malformed_count"] == 1
    assert audit["tombstone_rollup_verification"]["drift"] == verified["drift"]
    assert repair["repaired"] is False
    assert repair["reason"] == "audit_incomplete"
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("changes", [{"rollup": False}, {"event": "changed-event"}])
def test_damaged_rollup_marker_cannot_hide_rollup(tmp_path, changes):
    path = login_audit_log_path(tmp_path)
    path.write_text(json.dumps(rollup(**changes)) + "\n", encoding="utf-8")
    verified = verify_login_audit_rollup(tmp_path)
    assert verified["verified"] is False
    assert verified["rollup_present"] is True
    assert "rollup_identity_invalid" in verified["drift"]
    assert read_login_scrub_audit(tmp_path)["tombstone_rollup_verification"]["verified"] is False


def test_damaged_tombstone_marker_cannot_hide_span_contradiction(tmp_path):
    path = login_audit_log_path(tmp_path)
    record = {
        "event": LOGIN_AUDIT_TOMBSTONE_EVENT, "tombstone": False,
        "pruned_at": "2024-01-15T00:00:00Z", "task_name": "still-here",
    }
    path.write_text(json.dumps(rollup()) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
    verdict = verify_login_audit_rollup(tmp_path)
    assert verdict["verified"] is False
    assert "tombstone_identity_invalid" in verdict["drift"]
    assert "span_survivor" in verdict["drift"]
    assert verdict["span_survivors"] == ["still-here"]


def test_in_memory_verifier_rejects_non_records():
    for records in ([None], [rollup(), []]):
        verdict = verify_login_audit_rollup_records(records)
        assert verdict["verified"] is False
        assert verdict["malformed_count"] == 1
        assert "trail_malformed" in verdict["drift"]


def test_missing_and_empty_trails_are_distinguished_consistently(tmp_path):
    missing = tmp_path / "missing"
    for root in (missing, tmp_path):
        assert verify_login_audit_rollup(root)["reason"] == "no_trail"
        verdict = read_login_scrub_audit(root)["tombstone_rollup_verification"]
        assert verdict["reason"] == "no_trail"
        assert verdict["verified"] is False
    assert not missing.exists()
    path = login_audit_log_path(tmp_path)
    path.write_text("\n", encoding="utf-8")
    for verdict in (verify_login_audit_rollup(tmp_path),
                    read_login_scrub_audit(tmp_path)["tombstone_rollup_verification"]):
        assert verdict["verified"] is True
        assert verdict["reason"] == "no_rollup"


@pytest.mark.parametrize("failure", ["utf8", "permission", "directory"])
def test_unreadable_trails_never_verify(tmp_path, monkeypatch, failure):
    path = login_audit_log_path(tmp_path)
    if failure == "directory":
        path.mkdir()
    elif failure == "utf8":
        path.write_bytes(b"\xff\n")
    else:
        path.write_text(json.dumps(rollup()), encoding="utf-8")
        original = Path.read_text

        def denied(self, *args, **kwargs):
            if self == path:
                raise PermissionError("audit unavailable")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    for verdict in (verify_login_audit_rollup(tmp_path),
                    read_login_scrub_audit(tmp_path)["tombstone_rollup_verification"]):
        assert verdict["verified"] is False
        assert verdict["reason"] == "audit_read_failed"
        assert verdict["error"]
    repaired = repair_login_audit_rollup(tmp_path)
    assert repaired["repaired"] is False
    assert repaired["reason"] == "audit_read_failed"


def test_cli_surfaces_incomplete_trail_without_writing(tmp_path):
    path = login_audit_log_path(tmp_path)
    raw = b'{"event": "login_audit_tombstones_compacted",\n'
    path.write_bytes(raw)
    for command in ("loop-login-verify", "loop-login-audit"):
        result = CliRunner().invoke(unbound.app, [
            command, "--repo-path", str(tmp_path), "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        verdict = payload if command.endswith("verify") else payload["tombstone_rollup_verification"]
        assert verdict["verified"] is False
        assert verdict["drift"] == ["trail_malformed"]
    assert path.read_bytes() == raw
