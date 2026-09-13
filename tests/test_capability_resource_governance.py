"""Resource-governed invocation: violation attribution and durable quarantine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from blackhole_agent import capability_service as service
from blackhole_agent.capability_compounder import Capability
from blackhole_agent.process_capture import ResourceLimits, run_captured_process


def _completed(returncode: int, stderr: str = "", job_stats: dict | None = None):
    completed = subprocess.CompletedProcess(["tool"], returncode, "", stderr)
    if job_stats is not None:
        completed.job_stats = job_stats  # type: ignore[attr-defined]
    return completed


def test_peak_memory_at_limit_is_violation() -> None:
    limits = ResourceLimits(memory_bytes=256 << 20)
    stats = {"peak_job_memory_bytes": int((256 << 20) * 0.95)}
    violation = service.detect_resource_violation(_completed(1, job_stats=stats), limits)
    assert violation is not None
    assert violation["resource"] == "memory"
    assert violation["peak_job_memory_bytes"] == stats["peak_job_memory_bytes"]


def test_memory_error_stderr_is_violation_fallback() -> None:
    limits = ResourceLimits(memory_bytes=256 << 20)
    violation = service.detect_resource_violation(
        _completed(1, "Traceback ...\nMemoryError\n"), limits
    )
    assert violation is not None and violation["resource"] == "memory"


def test_ordinary_failure_is_not_violation() -> None:
    limits = ResourceLimits(memory_bytes=256 << 20)
    stats = {"peak_job_memory_bytes": 40 << 20}
    assert service.detect_resource_violation(
        _completed(1, "ValueError: bad input\n", job_stats=stats), limits
    ) is None
    assert service.detect_resource_violation(_completed(0), limits) is None


def test_capability_round_trip_preserves_quarantine() -> None:
    entry = Capability(
        id="capability.absorbed-x",
        name="x",
        description="d",
        kind="python",
        entry="m:f",
        proof_command="uv run python -c pass",
        resource_quarantine={"resource": "memory", "reason": "r"},
    )
    restored = Capability.from_dict(entry.to_dict())
    assert restored.resource_quarantine == {"resource": "memory", "reason": "r"}
    assert "resource_quarantine" not in Capability(
        id="capability.absorbed-y",
        name="y",
        description="d",
        kind="python",
        entry="m:f",
        proof_command="uv run python -c pass",
    ).to_dict()


def test_quarantine_recorded_and_refused_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "boom"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(
        "import json, sys\njson.load(sys.stdin)\nprint('{\"done\": 1}')\n", encoding="utf-8"
    )
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "boom",
                "name": "boom",
                "command": ["python", "tool.py"],
                "requires": ["seed"],
                "provides": ["done"],
                "cases": [
                    {"input": {"seed": "a"}, "expect": {"done": 1}},
                    {"input": {"seed": "b"}, "expect": {"done": 1}},
                ],
            }
        ),
        encoding="utf-8",
    )
    capability_id = "capability.absorbed-boom"
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    capability_id: {
                        "id": capability_id,
                        "name": "boom",
                        "last_proved_at": "2026-01-01T00:00:00Z",
                        "last_proof_exit_code": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    violation = {
        "resource": "memory",
        "reason": "peak committed memory hit the enforced limit",
        "limit_bytes": 1,
        "peak_job_memory_bytes": 1,
    }
    quarantine = service.record_resource_quarantine(root, capability_id, violation)
    assert quarantine is not None and quarantine["resource"] == "memory"
    document = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    assert document["capabilities"][capability_id]["resource_quarantine"]["reason"] == violation["reason"]

    with pytest.raises(service.InvocationError) as caught:
        service.invoke_capability(root, capability_id, {"seed": "a"})
    assert caught.value.status == 409
    assert caught.value.extra["violation"] == "resource_quarantined"


def _fixture_repo(tmp_path: Path, slug: str, tool_source: str, cases: list,
                  *, quarantined: bool = False) -> tuple[Path, str]:
    root = tmp_path / "repo"
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(tool_source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": slug,
                "command": ["python", "tool.py"],
                "requires": ["seed"],
                "provides": ["done"],
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )
    capability_id = f"capability.absorbed-{slug}"
    entry = {
        "id": capability_id,
        "name": slug,
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    if quarantined:
        entry["resource_quarantine"] = {
            "reason": "earlier run exceeded the memory limit",
            "resource": "memory",
            "limit_bytes": 1,
            "peak_job_memory_bytes": 1,
            "quarantined_at": "2026-01-01T00:00:00Z",
        }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": {capability_id: entry}}),
        encoding="utf-8",
    )
    return root, capability_id


_OK_TOOL = "import json, sys\njson.load(sys.stdin)\nprint('{\"done\": 1}')\n"
_FAIL_TOOL = "import sys\nsys.exit(3)\n"


def test_reproof_reinstates_quarantined_capability(tmp_path: Path) -> None:
    root, capability_id = _fixture_repo(
        tmp_path,
        "reform",
        _OK_TOOL,
        [
            {"input": {"seed": "a"}, "expect": {"done": 1}},
            {"input": {"seed": "b"}, "expect": {"done": 1}},
        ],
        quarantined=True,
    )
    with pytest.raises(service.InvocationError) as caught:
        service.invoke_capability(root, capability_id, {"seed": "a"})
    assert caught.value.status == 409

    verdict = service.reproof_capability(root, capability_id)
    assert verdict["reinstated"] is True
    assert verdict["cases_pass"] is True
    assert verdict["reproof_digest"]

    document = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    entry = document["capabilities"][capability_id]
    assert "resource_quarantine" not in entry
    assert entry["resource_reproof"]["cases_pass"] is True

    result = service.invoke_capability(root, capability_id, {"seed": "a"})
    assert result["ok"] is True and result["output"] == {"done": 1}


def test_reproof_keeps_quarantine_when_cases_fail(tmp_path: Path) -> None:
    root, capability_id = _fixture_repo(
        tmp_path,
        "broken",
        _FAIL_TOOL,
        [
            {"input": {"seed": "a"}, "expect": {"done": 1}},
            {"input": {"seed": "b"}, "expect": {"done": 1}},
        ],
        quarantined=True,
    )
    verdict = service.reproof_capability(root, capability_id)
    assert verdict["reinstated"] is False
    assert verdict["cases_pass"] is False
    document = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    quarantine = document["capabilities"][capability_id]["resource_quarantine"]
    assert "re-proof failed" in quarantine["reason"]

    with pytest.raises(service.InvocationError) as caught:
        service.invoke_capability(root, capability_id, {"seed": "a"})
    assert caught.value.status == 409


def test_reproof_refuses_non_quarantined_and_unknown(tmp_path: Path) -> None:
    root, capability_id = _fixture_repo(
        tmp_path,
        "healthy",
        _OK_TOOL,
        [
            {"input": {"seed": "a"}, "expect": {"done": 1}},
            {"input": {"seed": "b"}, "expect": {"done": 1}},
        ],
    )
    with pytest.raises(service.InvocationError) as caught:
        service.reproof_capability(root, capability_id)
    assert caught.value.status == 409
    with pytest.raises(service.InvocationError) as caught:
        service.reproof_capability(root, "capability.absorbed-missing")
    assert caught.value.status == 404


def test_limits_override_validation() -> None:
    assert service._validated_limits_override(None) is None
    assert service._validated_limits_override("bogus") is None
    assert service._validated_limits_override({"memory_bytes": 1}) is None  # below floor
    assert service._validated_limits_override({"memory_bytes": 1 << 40}) is None  # above ceiling
    assert service._validated_limits_override({"max_processes": 0}) is None
    override = service._validated_limits_override(
        {"memory_bytes": 64 << 20, "max_processes": 8}
    )
    assert override == {"memory_bytes": 64 << 20, "max_processes": 8}


def test_effective_limits_resolution() -> None:
    default = service.effective_resource_limits({})
    assert default.memory_bytes == service.INVOKE_MEMORY_LIMIT_BYTES
    assert default.max_processes == service.INVOKE_MAX_PROCESSES
    override = service.effective_resource_limits(
        {"limits_override": {"memory_bytes": 64 << 20, "max_processes": 8}}
    )
    assert override.memory_bytes == 64 << 20
    assert override.max_processes == 8
    ignored = service.effective_resource_limits({"limits_override": {"memory_bytes": 1}})
    assert ignored.memory_bytes == service.INVOKE_MEMORY_LIMIT_BYTES


def test_reproof_reports_enforced_limits_and_profile(tmp_path: Path) -> None:
    root, capability_id = _fixture_repo(
        tmp_path,
        "policy",
        _OK_TOOL,
        [
            {"input": {"seed": "a"}, "expect": {"done": 1}},
            {"input": {"seed": "b"}, "expect": {"done": 1}},
        ],
        quarantined=True,
    )
    verdict = service.reproof_capability(root, capability_id)
    assert verdict["reinstated"] is True
    assert verdict["enforced_limits"]["memory_bytes"] == service.INVOKE_MEMORY_LIMIT_BYTES
    if sys.platform == "win32":
        assert verdict["resource_profile"]["peak_job_memory_bytes"] > 0
        document = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
        profile = document["capabilities"][capability_id]["resource_profile"]
        assert profile["peak_job_memory_bytes"] > 0
        assert profile["observed_under_limit_bytes"] == service.INVOKE_MEMORY_LIMIT_BYTES


@pytest.mark.skipif(sys.platform != "win32", reason="job memory limits are enforced via Windows job objects")
def test_run_captured_process_enforces_memory_limit(tmp_path: Path) -> None:
    script = tmp_path / "hog.py"
    script.write_text(
        "chunks = []\n"
        "for _ in range(48):\n"
        "    chunk = bytearray(16 << 20)\n"
        "    for i in range(0, len(chunk), 4096):\n"
        "        chunk[i] = 1\n"
        "    chunks.append(chunk)\n",
        encoding="utf-8",
    )
    completed = run_captured_process(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout=60,
        resource_limits=ResourceLimits(memory_bytes=256 << 20, max_processes=8),
    )
    assert completed.returncode != 0
    stats = completed.job_stats  # type: ignore[attr-defined]
    assert stats["peak_job_memory_bytes"] >= int((256 << 20) * service.MEMORY_VIOLATION_PEAK_RATIO)
    violation = service.detect_resource_violation(
        completed, ResourceLimits(memory_bytes=256 << 20)
    )
    assert violation is not None and violation["resource"] == "memory"


def test_run_captured_process_unlimited_still_works(tmp_path: Path) -> None:
    script = tmp_path / "ok.py"
    script.write_text("print('hello')", encoding="utf-8")
    completed = run_captured_process(
        [sys.executable, str(script)], cwd=tmp_path, timeout=30
    )
    assert completed.returncode == 0
    assert "hello" in completed.stdout
