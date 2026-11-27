"""A real validator holds a port and inherits both output streams until released."""

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


OEM_OUTPUT = b"\xb2\xe2\xca\xd4" * 20000 + b"end"


def validator(mode):
    if mode == "parent":
        return subprocess.call([sys.executable, __file__, "worker"])
    if mode == "oem":
        sys.stdout.buffer.write(OEM_OUTPUT)
        return 0
    for stream, fill, marker in ((sys.stdout, "🌙", "stdout ready!"), (sys.stderr, "界", "stderr ready!")):
        stream.buffer.write((fill * 8000 + marker).encode("utf-8"))
        stream.buffer.flush()
    if mode != "worker":
        return int(mode)
    with socket.socket() as lease:
        lease.bind(("127.0.0.1", 0))
        Path("port.tmp").write_text(str(lease.getsockname()[1]), encoding="ascii")
        Path("port.tmp").replace("port")
        # The old Windows pipe reader can wait for this child after killing its shell.
        # A bounded wait lets the baseline finish and records any surviving writer.
        deadline = time.monotonic() + 7
        while not Path("release").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        Path("late").touch()
    return 0


def port_is_free(port):
    with socket.socket() as lease:
        try:
            lease.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def observe():
    from blackhole_agent.unbound import replay_validation_command

    quote = subprocess.list2cmdline if os.name == "nt" else shlex.join
    observed = {}
    passed = True
    with tempfile.TemporaryDirectory(prefix="bh-validator-") as directory:
        root = Path(directory)
        shutil.copyfile(__file__, root / "validator.py")
        for mode, exit_code in (("parent", None), ("23", 23), ("0", 0)):
            command = quote([sys.executable, "validator.py", mode])
            receipt = replay_validation_command(root, command, timeout=2 if mode == "parent" else 10)
            out, err = receipt["stdout_tail"], receipt["stderr_tail"]
            exact = (out == ("🌙" * 4000 + "stdout ready!")[-4000:]
                     and err == ("界" * 4000 + "stderr ready!")[-4000:])
            status = receipt["timed_out"], receipt["reproduced_exit_code"], receipt["ok"]
            passed &= exact and status == (exit_code is None, exit_code, exit_code == 0)
            observed[mode] = {
                "timed_out": receipt["timed_out"], "exit": receipt["reproduced_exit_code"], "ok": receipt["ok"],
                "characters": [len(out), len(err)], "exact_tails": exact,
            }
            if mode == "parent":
                port_file = root / "port"
                port = int(port_file.read_text()) if port_file.exists() else None
                observed["port_released_on_return"] = bool(port and port_is_free(port))
                (root / "release").touch()
                deadline = time.monotonic() + 2
                while port and not port_is_free(port) and time.monotonic() < deadline:
                    time.sleep(0.02)
                observed["late_write"] = (root / "late").exists()
        if os.name == "nt":
            native = replay_validation_command(root, quote([sys.executable, "validator.py", "oem"]))
            observed["oem_text"] = native["ok"] and native["stdout_tail"] == OEM_OUTPUT.decode("oem", "replace")[-4000:]
            passed &= observed["oem_text"]
            if shutil.which("pwsh") or shutil.which("powershell"):
                command = "[Console]::Out.WriteLine('out'); [Console]::Error.WriteLine('err'); Start-Sleep -Seconds 10"
                ps = replay_validation_command(root, command, timeout=3)
                observed["powershell"] = [ps["timed_out"], ps["ok"], ps["stdout_tail"], ps["stderr_tail"]]
                passed &= observed["powershell"] == [True, False, "out\n", "err\n"]
    passed &= observed["port_released_on_return"] and not observed["late_write"]
    return {"passed": passed, "observed": observed}


def test_validation_deadline():
    outcome = observe()
    assert outcome["passed"], outcome["observed"]


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in {"parent", "worker", "23", "0", "oem"}:
        sys.exit(validator(sys.argv[1]))
    print(json.dumps(observe()))
