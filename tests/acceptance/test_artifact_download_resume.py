"""Resume an interrupted artifact transfer with curl after restarting the HTTP service."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import tracemalloc
from contextlib import contextmanager
from pathlib import Path

from blackhole_agent.capability_service import build_server


TOKEN = "download-fixture"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
WRITER = "capability.absorbed-file-writer"


def install_writer(root):
    tools = root / "capabilities"
    writer = tools / "absorbed" / "file-writer"
    writer.mkdir(parents=True)
    (writer / "tool.py").write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        "data = bytes(range(251)) * json.load(sys.stdin)['copies'] + b'original'\n"
        "(Path(os.environ['BLACKHOLE_EFFECT_DIR']) / 'output.bin').write_bytes(data)\n"
        "print(json.dumps({'size': len(data)}))\n", encoding="utf-8")
    manifest = dict(schema_version=1, slug="file-writer", name="Binary fixture", command=["python", "tool.py"],
                    requires=["copies"], provides=["size"], cases=[
                        {"input": {"copies": n}, "expect": {"size": 251 * n + 8}} for n in (1, 2)])
    (writer / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tools / "ledger.json").write_text(json.dumps({"capabilities": {WRITER: {"last_proof_exit_code": 0}}}),
                                       encoding="utf-8")


def server_process(root):
    with build_server(root, token=TOKEN) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            print(server.server_port, flush=True)
            for command in sys.stdin:
                if command.strip() == "measure":
                    tracemalloc.start()
                    print("ready", flush=True)
                else:
                    print(tracemalloc.get_traced_memory()[1], flush=True)
                    tracemalloc.stop()
        finally:
            server.shutdown()
            thread.join()


@contextmanager
def serving(root):
    with subprocess.Popen([sys.executable, __file__, "serve", str(root)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as worker:
        try:
            yield int(worker.stdout.readline()), worker
        finally:
            worker.stdin.close()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


def request(port, path, headers, limit=None, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("POST" if payload else "GET", path, headers=headers, body=payload)
        reply = connection.getresponse()
        return reply.status, reply.headers, reply.read(limit)
    finally:
        connection.close()


def observe(root):
    data = bytes(range(251)) * 50_000 + b"original"
    install_writer(root)
    saved = root / "client.part"
    with serving(root) as (port, _):
        created, _, raw = request(port, "/invoke", {**AUTH, "Content-Type": "application/json"},
                                  payload=json.dumps({"capability_id": WRITER, "input": {"copies": 50_000}}))
        invocation = json.loads(raw)
        if created != 200 or invocation.get("artifacts") != [{"name": "output.bin", "bytes": len(data)}]:
            raise RuntimeError(f"writer returned {created}: {invocation}")
        ident = invocation["invocation_id"]
        path = f"/artifacts/{ident}/output.bin"
        status, initial, prefix = request(port, path, AUTH, 196_613)
        saved.write_bytes(prefix)
    tag = initial.get("ETag", "")
    with serving(root) as (port, worker):
        worker.stdin.write("measure\n")
        worker.stdin.flush()
        assert worker.stdout.readline().strip() == "ready"
        resume = subprocess.run([
            "curl", "--disable", "--noproxy", "*", "--silent", "--show-error", "--max-time", "15",
            "--header", f"Authorization: Bearer {TOKEN}", "--header", f"If-Range: {tag}",
            "--continue-at", "-", "--output", str(saved), "--write-out", "%{http_code} %{size_download}",
            f"http://127.0.0.1:{port}{path}",
        ], capture_output=True, text=True, timeout=20)
        worker.stdin.write("finish\n")
        worker.stdin.flush()
        peak = int(worker.stdout.readline())
        rebuilt = saved.read_bytes() == data
        artifact = root / ".blackhole-agent" / "invocation-artifacts" / ident / "output.bin"
        original = artifact.stat()
        replacement = data[:-8] + b"replaced"
        artifact.write_bytes(replacement)
        os.utime(artifact, ns=(original.st_atime_ns, original.st_mtime_ns))
        stale, changed, whole = request(port, path, {**AUTH, "Range": "bytes=5-", "If-Range": tag})
        partial, window, suffix = request(port, path, {**AUTH, "Range": "bytes=-8"})
        eof, beyond, body = request(port, path, {**AUTH, "Range": f"bytes={len(data)}-"})
        unauthorized, _, _ = request(port, path, {"Range": "bytes=0-0"})
    sent = resume.stdout.strip()
    observed = dict(invoke=created, initial=status, prefix=len(prefix), total=len(data), curl_exit=resume.returncode,
                    resume_http_and_bytes=sent, reconstructed=rebuilt, peak_python_bytes=peak,
                    stale_status=stale, full_replacement=whole == replacement,
                    tag_changed=changed.get("ETag") not in (None, tag), suffix_status=partial,
                    suffix_range=window.get("Content-Range"), eof_status=eof,
                    eof_range=beyond.get("Content-Range"), unauthorized=unauthorized)
    passed = (status == 200 and tag.startswith('"') and tag.endswith('"') and
              initial.get("Accept-Ranges") == "bytes" and prefix == data[:196_613] and
              resume.returncode == 0 and sent == f"206 {len(data) - len(prefix)}" and rebuilt and
              peak < 4 * 1024 * 1024 and stale == 200 and whole == replacement and
              changed.get("ETag") not in (None, tag) and partial == 206 and suffix == b"replaced" and
              window.get("Content-Range") == f"bytes {len(data)-8}-{len(data)-1}/{len(data)}" and
              eof == 416 and beyond.get("Content-Range") == f"bytes */{len(data)}" and not body and
              unauthorized == 401)
    return passed, observed


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        server_process(Path(sys.argv[2]))
    else:
        try:
            with tempfile.TemporaryDirectory() as folder:
                passed, observed = observe(Path(folder))
        except Exception as exc:
            passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps({"passed": passed, "observed": observed}))
