import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from blackhole_agent.process_capture import run_captured_process
from blackhole_agent.unbound import continuous_loop_status_snapshot, pid_is_running, run_command


def test_capture_preserves_stdout_stderr_and_exit_code(tmp_path):
    result = run_captured_process(
        [sys.executable, "-c", "import sys;print('hello');print('error',file=sys.stderr);sys.exit(7)"],
        cwd=tmp_path, timeout=5,
    )
    assert result.returncode == 7
    assert result.stdout.strip() == "hello"
    assert result.stderr.strip() == "error"


def test_capture_decodes_invalid_utf8_without_crashing(tmp_path):
    result = run_captured_process([sys.executable, "-c", "import os;os.write(1,b'hello\\xff')"], cwd=tmp_path, timeout=5)
    assert result.stdout == "hello\ufffd"


def test_capture_pipes_stdin_input(tmp_path):
    result = run_captured_process(
        [sys.executable, "-c", "import sys;sys.stdout.write(sys.stdin.read())"],
        cwd=tmp_path, timeout=5, input="seeded prompt \u4f60\u597d",
    )
    assert result.returncode == 0
    assert result.stdout == "seeded prompt \u4f60\u597d"


def test_capture_reports_missing_executable(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_captured_process([str(tmp_path / "missing-command.exe")], cwd=tmp_path, timeout=5)


def test_bootstrap_preserves_command_arguments_cwd_environment_and_stdin(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKHOLE_COMMAND_TEST", "inherited-value")
    argument = 'Unicode \u4f60\u597d with spaces "quotes" and \\slashes'
    code = (
        "import json,os,sys;"
        "print(json.dumps([sys.argv[1],os.getcwd(),os.environ['BLACKHOLE_COMMAND_TEST'],sys.stdin.read()]))"
    )
    result = run_captured_process([sys.executable, "-c", code, argument], cwd=tmp_path, timeout=5)
    assert result.returncode == 0
    assert json.loads(result.stdout) == [argument, str(tmp_path), "inherited-value", ""]


@pytest.mark.skipif(os.name != "nt", reason="Windows DWORD status")
def test_capture_preserves_windows_crash_status(tmp_path):
    result = run_captured_process(
        [sys.executable, "-c", "import ctypes;ctypes.windll.kernel32.ExitProcess(3221225477)"],
        cwd=tmp_path, timeout=5,
    )
    assert result.returncode == 3221225477


@pytest.mark.skipif(os.name != "nt", reason="Windows job assignment")
def test_job_assignment_failure_cannot_start_the_requested_command(tmp_path, monkeypatch):
    from blackhole_agent._windows_job import WindowsJob

    marker = tmp_path / "must-not-start"
    job = WindowsJob()
    monkeypatch.setattr(job.api, "AssignProcessToJobObject", lambda *_: False)
    try:
        with pytest.raises(OSError):
            job.start(
                [sys.executable, "-c", f"from pathlib import Path;Path({str(marker)!r}).touch()"],
                cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                error_path=tmp_path / "startup-error",
            )
        assert not marker.exists()
    finally:
        job.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows kill-on-job-close")
def test_controller_death_stops_its_command_without_touching_other_processes(tmp_path):
    import blackhole_agent.process_capture as capture

    marker = tmp_path / "owned.pid"
    worker = (
        "import os,time;from pathlib import Path;"
        f"Path({str(marker)!r}).write_text(str(os.getpid()));"
        "time.sleep(15)"
    )
    owner_code = (
        f"import sys;sys.path.insert(0,{str(Path(capture.__file__).resolve().parents[1])!r});"
        "from pathlib import Path;from blackhole_agent.process_capture import run_captured_process;"
        f"run_captured_process({[sys.executable, '-c', worker]!r},cwd=Path({str(tmp_path)!r}),timeout=30)"
    )
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(15)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    owner = subprocess.Popen([sys.executable, "-I", "-c", owner_code],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "owned command did not start"
        pid = int(marker.read_text())
        assert pid_is_running(pid)
        owner.kill()
        owner.wait(timeout=5)
        deadline = time.monotonic() + 3
        while pid_is_running(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not pid_is_running(pid)
        assert unrelated.poll() is None
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=5)
        unrelated.kill()
        unrelated.wait(timeout=5)


def test_timeout_terminates_owned_parent_and_child_without_pipe_eof_wait(tmp_path):
    child_pid_file = tmp_path / "child.json"
    code = (
        "import subprocess,sys,time,json;from pathlib import Path;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"Path({str(child_pid_file)!r}).write_text(json.dumps(p.pid));"
        "print('checkout started',flush=True);time.sleep(60)"
    )
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired) as caught:
            run_captured_process([sys.executable, "-u", "-c", code], cwd=tmp_path, timeout=2)
        assert time.monotonic() - started < 18  # Includes a bounded 10+5-second cleanup grace.
        assert "checkout started" in caught.value.stdout
        assert child_pid_file.is_file()
        child_pid = json.loads(child_pid_file.read_text())
        assert not pid_is_running(child_pid)
        assert unrelated.poll() is None  # Never kill all Python/Git/CLI processes.
    finally:
        unrelated.kill()
        unrelated.wait(timeout=5)


def test_run_command_checks_failures_and_uses_bounded_capture(tmp_path, monkeypatch):
    calls = []

    def capture(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, "", "specific failure")

    monkeypatch.setattr("blackhole_agent.unbound.run_captured_process", capture)
    with pytest.raises(RuntimeError, match="specific failure"):
        run_command(["git", "status"], cwd=tmp_path, timeout=12)
    assert calls[0][1]["timeout"] == 12
    assert run_command(["git", "status"], cwd=tmp_path, check=False).returncode == 1


@pytest.mark.parametrize("status", ["running", "creating_mission", "running_mission", "sleeping", "publishing"])
def test_loop_status_flags_dead_owner_without_rewriting_durable_state(monkeypatch, status):
    monkeypatch.setattr("blackhole_agent.unbound.pid_is_running", lambda _: False)
    original = {"status": status, "pid": 123, "last_error": ""}
    result = continuous_loop_status_snapshot(original)
    assert result["effective_status"] == "orphaned"
    assert not result["pid_alive"]
    assert original == {"status": status, "pid": 123, "last_error": ""}


def test_stopped_loop_is_not_marked_as_an_orphan(monkeypatch):
    monkeypatch.setattr("blackhole_agent.unbound.pid_is_running", lambda _: False)
    assert continuous_loop_status_snapshot({"status": "stopped", "pid": "bad"})["effective_status"] == "stopped"


def test_live_pid_is_only_a_liveness_observation(monkeypatch):
    monkeypatch.setattr("blackhole_agent.unbound.pid_is_running", lambda _: True)
    result = continuous_loop_status_snapshot({"status": "running_mission", "pid": 123})
    assert result["pid_alive"] and result["effective_status"] == "running_mission"
    assert "healthy" not in result
