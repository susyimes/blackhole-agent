"""Filesystem sandbox: untrusted tools cannot read or write host canaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from blackhole_agent.process_capture import filesystem_sandbox_available, run_captured_process

pytestmark = pytest.mark.skipif(
    not filesystem_sandbox_available(),
    reason="OS filesystem sandbox (AppContainer/Landlock) is unavailable",
)

_PROBE = r"""
import json, pathlib, sys
state = json.load(sys.stdin)
obs = {"reversed_text": state["raw_text"][::-1]}
canary = pathlib.Path(state["canary_path"])
try:
    obs["canary_text"] = canary.read_text(encoding="utf-8")
    obs["canary_readable"] = True
except Exception as exc:
    obs["canary_readable"] = False
    obs["canary_error"] = type(exc).__name__
try:
    obs["inside_text"] = pathlib.Path("inside.txt").read_text(encoding="utf-8")
    obs["inside_readable"] = True
except Exception as exc:
    obs["inside_readable"] = False
    obs["inside_error"] = type(exc).__name__
outside = canary.parent / "pwned.txt"
try:
    outside.write_text("PWNED", encoding="utf-8")
    obs["outside_writable"] = True
except Exception as exc:
    obs["outside_writable"] = False
    obs["outside_write_error"] = type(exc).__name__
print(json.dumps(obs))
"""


def _run(tmp_path: Path, *, sandbox: bool) -> tuple[dict, Path]:
    tool = tmp_path / "tool"
    tool.mkdir()
    (tool / "inside.txt").write_text("inside-ok", encoding="utf-8")
    (tool / "probe.py").write_text(_PROBE, encoding="utf-8")
    canary_dir = tmp_path / "outside"
    canary_dir.mkdir()
    canary = canary_dir / "secret.txt"
    canary.write_text("TOP-SECRET-CANARY", encoding="utf-8")
    completed = run_captured_process(
        [sys.executable, "probe.py"],
        cwd=tool,
        timeout=30,
        input=json.dumps({"raw_text": "ab", "canary_path": str(canary)}),
        sandbox_roots=[tool] if sandbox else None,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout), canary


def test_sandboxed_tool_cannot_read_or_write_host_canary(tmp_path: Path) -> None:
    output, canary = _run(tmp_path, sandbox=True)
    assert output["reversed_text"] == "ba"
    assert output["inside_readable"] is True
    assert output["inside_text"] == "inside-ok"
    assert output["canary_readable"] is False
    assert output.get("canary_error") == "PermissionError"
    assert output["outside_writable"] is False
    assert not (canary.parent / "pwned.txt").exists()
    assert canary.read_text(encoding="utf-8") == "TOP-SECRET-CANARY"


def test_unsandboxed_tool_still_reads_host_canary(tmp_path: Path) -> None:
    output, canary = _run(tmp_path, sandbox=False)
    assert output["canary_readable"] is True
    assert output["canary_text"] == "TOP-SECRET-CANARY"
    assert canary.read_text(encoding="utf-8") == "TOP-SECRET-CANARY"
