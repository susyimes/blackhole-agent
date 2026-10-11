"""Acceptance probe: the live invocation plane can serve HTTPS.

Bearer tokens and POST /invoke payloads currently travel as cleartext HTTP
even when an operator supplies a token. This probe starts the invocation
plane as a separate OS process and requires:

1. ``serve --tls-cert/--tls-key`` listens; the readiness line reports
   ``tls=true``; HTTPS GET /health reports ``tls=true``.
2. HTTPS POST /invoke of the fixture text-reverser returns the declared
   reverse output.
3. An HTTP client to the same TLS port does not receive JSON health.
4. ``serve --tls-cert`` pointing at a missing file prints JSON
   ``error=tls_cert_unreadable`` (or ``tls_key_unreadable`` /
   ``tls_requires_cert_and_key``) and never listens.
5. ``serve`` without TLS flags still answers HTTP GET /health with
   ``tls=false`` and a follow-up HTTP POST /invoke still returns the
   declared reverse output.

On the pre-mission plane ``--tls-cert`` is unknown or the socket stays
HTTP, so HTTPS health/invoke fail. Both outcomes exit 0 with JSON
``passed`` and nonempty ``observed``.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

PROBE_TEXT = "tls-invoke-e5d89abd"
EXPECTED = PROBE_TEXT[::-1]
TLS_ERRORS = {
    "tls_cert_unreadable",
    "tls_key_unreadable",
    "tls_requires_cert_and_key",
    "tls_cert_invalid",
}

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_UNVERIFIED_TLS = ssl._create_unverified_context()

# Embedded because the controller copies only this .py into a temp dir.
TLS_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDIzCCAgugAwIBAgIQY6UP76QUVY1FOzWdfkTZRTANBgkqhkiG9w0BAQsFADAUMRIwEAYDVQQD
DAlsb2NhbGhvc3QwHhcNMjYxMDExMDc1OTQ5WhcNMzYxMDExMDgwOTQ3WjAUMRIwEAYDVQQDDAls
b2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCfnYTDFJijE4xJ1SS5CT61
4375r/gDrVH9i8h48qLWvL/y2arGIERAZqrdEJRgqns24Rg0UYfQSxqIoqt/sXMTr+z8o7MusfDG
Xg8vdhcmLzO67AVtWxgnmz+zyGNCuSRwVfH3sUBEPGTgpSbs/dLyLnLqgXuTs8OriwRHJhiMe2qd
fpqdrPNeQEVGfWK9kFfciDeOkijaUM8cijJwAhsj76t6ZYVlwGhnoZT60piaaw3sT3nnDwMzeU5O
hvBmD645Ipv1DPuPjp2ZLZ/f933QP+eLaw1USq4qzKowdryHeUlwrUFufXQ5w4QIXEYttUv6Ggnt
8dDBSvtglx7Jt19tAgMBAAGjcTBvMA4GA1UdDwEB/wQEAwIFoDAdBgNVHSUEFjAUBggrBgEFBQcD
AgYIKwYBBQUHAwEwHwYDVR0RBBgwFoIJbG9jYWxob3N0ggkxMjcuMC4wLjEwHQYDVR0OBBYEFCNR
X2B8CK38g1XPmoaCfNzlB6R0MA0GCSqGSIb3DQEBCwUAA4IBAQAlInY0g+XmDdC4Cwv48Q1EHvrj
urepDzJMJPpCUMdC/k9V9q2fTkkjPdYTvRzdaAfGKFxhPO39OqIotjqWjEBjT2al9iC6/9nop3zW
bcXtMohSI19/XsPNbGM2I55NDzjnKv60GPtRTVTA19pj8kxeWB5geKa527tYX58H0Rx5hRNrrZEi
1ihmIwuxVTgzS9U8WdczsrbMofnYgN8RUdSE3Xm3l9GmpGMZ1PZnsdHJiEypW+JcZ7b4nNhACCDx
7u/TaigqrAmU6x9Milp10rBBfBc0CYWW5gUzrSp7K0jxowWfjhXYB5m3zSMaK0+tNDXd7k6CkpAt
LzS4CIr8xAif
-----END CERTIFICATE-----
"""

TLS_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEzAIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCfnYTDFJijE4xJ1SS5CT614375
r/gDrVH9i8h48qLWvL/y2arGIERAZqrdEJRgqns24Rg0UYfQSxqIoqt/sXMTr+z8o7MusfDGXg8v
dhcmLzO67AVtWxgnmz+zyGNCuSRwVfH3sUBEPGTgpSbs/dLyLnLqgXuTs8OriwRHJhiMe2qd
fpqdrPNeQEVGfWK9kFfciDeOkijaUM8cijJwAhsj76t6ZYVlwGhnoZT60piaaw3sT3nnDwMzeU5O
hvBmD645Ipv1DPuPjp2ZLZ/f933QP+eLaw1USq4qzKowdryHeUlwrUFufXQ5w4QIXEYttUv6Ggnt
8dDBSvtglx7Jt19tAgMBAAECggEAFJC7FleFAx31qV2pCZ5DUjQpnAosLm0ab0yfW9YHXRucr7GT60sl
ABc6VJlaRMoybfO6pqMKmK/Uj15GMoGujg7Qvgxpfc63cxeTZU4V1XmndKIMYPanuhKqtoNPJr2s
ED1Cm+NeoGwXo0okJczebQ3HCKf+QB2dTHDw8CncZ90a0mhPthFWf5tnqLODyP6zb59g+utXaXbZ
by5T28UTIft13nuB0fY6PzuDy4fd8Al5b/kdfCDQUnuc1z8dnrN6lgcn1Dsbcb0LJuQWlcgHZylw
d/vkaWwpi+8qzbwOZ4hpaunP55Xt5Gulqrjn2sgWXWN9UdBRrxxuI9xmWQFTkQKBgQDSJKS5NBbW
hAPuKl07R/WQTSwHv/o3+nkoMgYF8jwWMSjGiBD2aJmRaalSc3dUhYcl46VFMzAalCn44oU5fuVD
CzpFtRtQBAf7SyR0JlB0zPFtbDiwZ3voPrJXpuB2Cib8Kf5XIOOxkNgPVPwNnRCAZMWHAFEfCf8J
1fi7QEQRowKBgQDCcjUh2xAXuwMAhSuJ6jDG4hoTmlEMf9mBI8NDWQAkBZ3J2Dczv+i+VIC3tDyK
TLErx5ZGAaf1vaEXAK85k5PiV3NBaPcjF1W8QiyodHMYj1jq3AChZweuB3zz63xw0zdZ6Jn4sRt5
V4BPw04x55iDJAIWWjxMWhj47hqfhdJ7rwKBgQCV9sJ6zJpzsbhgUWlBMeQje38tdKorIpstvS0h
NzH8IE7aByYbwp+87ut/xJjm/3dn6aH61UHB5fRiAb1TP6R6iNun/UuleYr8oS49mU4XXF36WZ3G
/cKmBYAeHx/V/P6/O3SfVwBGqngV0O8jA/BPwBpacjZx8R9JNKKRdpZdAwKBgBKb23nh/ShIPYFP
PVt1jjV6bgRyQE9x7N7vDUDkw56u6urmRmIte5i7fZYXKbQSouINt9P7VJewDjqlVh+sf/qpY95e
rUguc4YQzzVP77PqBBh19Zl8wr9k+BBf+QjTLfjsyc+DI535Qc5gYptkDrR+PbTl7d9gwAMSxnl9
1ScBAoGATj/tNlIXPtuM34jdCNWCJhFo7rHS7EtpWx70Ms5D34FpOyHGMmySsPfFN7T3ML6HeBxA
GoqLz5I4C6yL1vjm7VVL3YQbQBcMnbHklnZOp6rvNRoLpHg4cCZWmYXoPQ8VjRZ7bd9o61mFG1Qx
PWzXRpfdZyNlAmTKJmz0bFCdzgigDTALBgNVHQ8xBAMCAJA=
-----END PRIVATE KEY-----
"""


def _ledger_entry(capability_id: str, name: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {
                        "input": {key: "x" for key in requires},
                        "expect": {provides[0]: "x"},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _tls_pair(directory: Path) -> tuple[Path, Path]:
    cert = directory / "tls-cert.pem"
    key = directory / "tls-key.pem"
    cert.write_text(TLS_CERT_PEM, encoding="ascii")
    key.write_text(TLS_KEY_PEM, encoding="ascii")
    return cert, key


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    timeout: int = 15,
    context: ssl.SSLContext | None = None,
) -> tuple[int | None, object, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
            try:
                return response.status, json.loads(raw.decode("utf-8")), ""
            except Exception:
                return response.status, None, raw[:200].decode("latin1", errors="replace")
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8")), ""
        except Exception:
            return exc.code, None, raw[:200].decode("latin1", errors="replace")
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _serve_env(src_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("BLACKHOLE_INVOCATION_TOKEN", None)
    env.pop("BLACKHOLE_TLS_CERT", None)
    env.pop("BLACKHOLE_TLS_KEY", None)
    return env


def _start_serve(root: Path, src_root: Path, extra_args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "blackhole_agent.capability_service",
            "serve",
            "--port",
            "0",
            "--root",
            str(root),
            *extra_args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_serve_env(src_root),
    )


def _wait_json_line(process: subprocess.Popen, timeout: float = 60.0) -> dict[str, object]:
    sink: dict[str, object] = {}

    def reader() -> None:
        try:
            line = process.stdout.readline() if process.stdout else ""
            sink["line"] = line[:1000] if isinstance(line, str) else ""
            sink["payload"] = json.loads(line) if line else None
        except Exception as exc:
            sink["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    process.poll()
    sink["returncode"] = process.returncode
    return sink


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-tls"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="invocation-tls-probe-", ignore_cleanup_errors=True)
    processes: list[subprocess.Popen] = []
    try:
        base_dir = Path(scratch.name)
        root = _build_fixture_root(base_dir)
        cert, key = _tls_pair(base_dir)

        missing = _start_serve(
            root,
            src_root,
            ["--tls-cert", str(base_dir / "missing-cert.pem"), "--tls-key", str(key)],
        )
        processes.append(missing)
        refused = _wait_json_line(missing, timeout=20)
        try:
            missing.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        refused["returncode"] = missing.poll()
        refused_payload = refused.get("payload") if isinstance(refused.get("payload"), dict) else {}
        observed["missing_cert"] = {
            "returncode": refused.get("returncode"),
            "payload": refused_payload,
            "line": refused.get("line"),
            "error": refused.get("error"),
        }
        missing_ok = (
            refused.get("returncode") not in (None, 0)
            and isinstance(refused_payload, dict)
            and refused_payload.get("ok") is False
            and str(refused_payload.get("error") or "") in TLS_ERRORS
            and refused_payload.get("listening") is None
        )

        tls_proc = _start_serve(
            root,
            src_root,
            ["--tls-cert", str(cert), "--tls-key", str(key)],
        )
        processes.append(tls_proc)
        ready = _wait_json_line(tls_proc, timeout=30)
        ready_payload = ready.get("payload") if isinstance(ready.get("payload"), dict) else {}
        observed["tls_ready"] = {
            "returncode": ready.get("returncode"),
            "payload": ready_payload,
            "line": ready.get("line"),
            "error": ready.get("error"),
        }
        listening = ready_payload.get("listening") if isinstance(ready_payload, dict) else None
        tls_listening = (
            tls_proc.poll() is None
            and isinstance(ready_payload, dict)
            and ready_payload.get("tls") is True
            and isinstance(listening, int)
            and listening > 0
        )
        https_health_ok = False
        https_invoke_ok = False
        http_blocked = False
        if isinstance(listening, int) and listening > 0:
            https_base = f"https://127.0.0.1:{listening}"
            health_status, health, health_err = _request(
                "GET", f"{https_base}/health", context=_UNVERIFIED_TLS
            )
            observed["https_health"] = {
                "status": health_status,
                "body": health,
                "error": health_err,
            }
            https_health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and health.get("tls") is True
            )
            invoke_status, invoked, invoke_err = _request(
                "POST",
                f"{https_base}/invoke",
                {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": PROBE_TEXT}},
                context=_UNVERIFIED_TLS,
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["https_invoke"] = {
                "status": invoke_status,
                "output": output,
                "error": invoke_err,
            }
            https_invoke_ok = (
                invoke_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )
            http_status, http_body, http_err = _request(
                "GET", f"http://127.0.0.1:{listening}/health", timeout=5
            )
            observed["http_on_tls"] = {
                "status": http_status,
                "body": http_body,
                "error": http_err,
            }
            http_blocked = not (
                http_status == 200
                and isinstance(http_body, dict)
                and http_body.get("ok") is True
            )

        http_proc = _start_serve(root, src_root, [])
        processes.append(http_proc)
        http_ready = _wait_json_line(http_proc, timeout=30)
        http_payload = http_ready.get("payload") if isinstance(http_ready.get("payload"), dict) else {}
        observed["http_ready"] = {
            "returncode": http_ready.get("returncode"),
            "payload": http_payload,
            "error": http_ready.get("error"),
        }
        http_port = http_payload.get("listening") if isinstance(http_payload, dict) else None
        http_health_ok = False
        http_invoke_ok = False
        if isinstance(http_port, int) and http_port > 0:
            http_base = f"http://127.0.0.1:{http_port}"
            h_status, h_body, h_err = _request("GET", f"{http_base}/health")
            observed["http_health"] = {"status": h_status, "body": h_body, "error": h_err}
            http_health_ok = (
                h_status == 200
                and isinstance(h_body, dict)
                and h_body.get("ok") is True
                and h_body.get("tls") is False
            )
            i_status, i_body, i_err = _request(
                "POST",
                f"{http_base}/invoke",
                {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": PROBE_TEXT}},
            )
            i_output = i_body.get("output") if isinstance(i_body, dict) else None
            observed["http_invoke"] = {"status": i_status, "output": i_output, "error": i_err}
            http_invoke_ok = (
                i_status == 200
                and isinstance(i_output, dict)
                and i_output.get("reversed_text") == EXPECTED
            )

        checks = {
            "missing_cert_refused": missing_ok,
            "tls_listening": tls_listening,
            "https_health_tls": https_health_ok,
            "https_invoke_reverse": https_invoke_ok,
            "http_client_blocked_on_tls": http_blocked,
            "http_health_tls_false": http_health_ok,
            "http_invoke_still_works": http_invoke_ok,
        }
        observed["checks"] = checks
        return {"passed": all(checks.values()), "observed": observed}
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    finally:
        for process in processes:
            _stop(process)
        scratch.cleanup()


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict), flush=True)
    sys.exit(0)
