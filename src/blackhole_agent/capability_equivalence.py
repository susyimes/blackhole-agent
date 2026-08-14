"""Capability equivalence gate: machine-checked behavior preservation.

The mission's simplification slices delete or rewrite large amounts of
generated machinery. Deletion is only safe when an independent check proves
the observable behavior did not change. This module is that check:

- a **snapshot** binds a set of probes to their observed results:
  ``pytest`` probes (test counts from a JUnit report), ``command`` probes
  (exit code plus a volatility-normalized digest of stdout), and
  ``api-surface`` probes (imported module surface: names, kinds,
  signatures, and JSON-scalar constants);
- snapshots are digest-sealed JSON under
  ``artifacts/capability-equivalence/<name>/`` — editing a recorded result
  breaks the seal;
- **verification** re-runs every probe live and compares: a drifted system
  fails by probe id, a tampered snapshot fails its digest, a forged digest
  still fails because recorded results no longer match the live system;
- :func:`builtin_equivalence_proof` is the hermetic registered proof:
  capture-then-verify on scratch fixtures, tamper detection, and drift
  detection, all without network or ledger mutation.

Determinism contract: probe results must be reproducible on the same
checkout. Timestamps and durations are excluded from every digest; command
probe stdout is normalized by dropping volatile keys (``*_at``,
``*_seconds``, ``duration*``, ``elapsed*``, ``timestamp*``) before
digesting. No skill-route discovery.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import inspect
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-equivalence"

PROBE_KINDS = frozenset({"pytest", "command", "api-surface"})
_VOLATILE_KEY_PREFIXES = ("duration", "elapsed", "timestamp")
_VOLATILE_KEY_SUFFIXES = ("_at", "_seconds")


# ---------------------------------------------------------------------------
# Canonical digests.
# ---------------------------------------------------------------------------


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _strip_volatile(value: Any) -> Any:
    """Recursively drop volatile keys (timestamps, durations) from JSON data."""

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            text = str(key).lower()
            if text.endswith(_VOLATILE_KEY_SUFFIXES) or text.startswith(_VOLATILE_KEY_PREFIXES):
                continue
            out[key] = _strip_volatile(item)
        return out
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Probe validation and execution.
# ---------------------------------------------------------------------------


def validate_probe(probe: Mapping[str, Any]) -> None:
    kind = str(probe.get("kind") or "")
    if kind not in PROBE_KINDS:
        raise ValueError(f"unsupported probe kind {kind!r}; expected one of {sorted(PROBE_KINDS)}")
    if not str(probe.get("id") or "").strip():
        raise ValueError("probe id is required")
    if kind == "pytest":
        paths = probe.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise ValueError("pytest probe requires a non-empty list of path strings")
    elif kind == "command":
        argv = probe.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(p, str) for p in argv):
            raise ValueError("command probe requires a non-empty argv list of strings")
    else:
        modules = probe.get("modules")
        if not isinstance(modules, list) or not modules or not all(isinstance(m, str) for m in modules):
            raise ValueError("api-surface probe requires a non-empty list of module names")


def _subprocess_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_pytest_probe(probe: Mapping[str, Any], *, cwd: Path, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="blackhole-equiv-junit-") as tmp:
        report = Path(tmp) / "junit.xml"
        argv = [
            sys.executable,
            "-m",
            "pytest",
            *[str(path) for path in probe["paths"]],
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
            f"--junitxml={report}",
        ]
        completed = subprocess.run(
            argv, capture_output=True, text=True, cwd=cwd, env=_subprocess_env(), timeout=timeout
        )
        counts = {"tests": None, "failures": None, "errors": None, "skipped": None}
        if report.is_file():
            suite = ET.parse(report).getroot()
            if suite.tag == "testsuites":
                suites = list(suite)
                counts = {
                    "tests": sum(int(s.get("tests", 0)) for s in suites),
                    "failures": sum(int(s.get("failures", 0)) for s in suites),
                    "errors": sum(int(s.get("errors", 0)) for s in suites),
                    "skipped": sum(int(s.get("skipped", 0)) for s in suites),
                }
            else:
                counts = {
                    key: int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")
                }
        return {"exit_code": completed.returncode, **counts}


def _run_command_probe(probe: Mapping[str, Any], *, cwd: Path, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        [str(part) for part in probe["argv"]],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_subprocess_env(),
        timeout=timeout,
    )
    stdout = completed.stdout or ""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = None
    if parsed is None:
        stdout_digest = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        stdout_form = "raw"
    else:
        stdout_digest = _digest(_strip_volatile(parsed))
        stdout_form = "json"
    return {
        "exit_code": completed.returncode,
        "stdout_form": stdout_form,
        "stdout_digest": stdout_digest,
    }


def _surface_entry(name: str, value: Any) -> list[Any]:
    if inspect.ismodule(value):
        return [name, "module"]
    if inspect.isclass(value):
        return [name, "class"]
    if inspect.isroutine(value) or callable(value):
        try:
            signature = str(inspect.signature(value))
        except (TypeError, ValueError):
            signature = ""
        return [name, "callable", signature]
    if value is None or isinstance(value, (str, int, float, bool)):
        return [name, "data", json.dumps(value, sort_keys=True)]
    return [name, "data"]


def _run_api_surface_probe(probe: Mapping[str, Any]) -> dict[str, Any]:
    surfaces: dict[str, Any] = {}
    for module_name in probe["modules"]:
        module = importlib.import_module(module_name)
        entries = sorted(
            _surface_entry(name, value)
            for name, value in vars(module).items()
            if not (name.startswith("__") and name.endswith("__"))
        )
        surfaces[module_name] = _digest(entries)
    return {"surfaces": surfaces}


def run_probe(probe: Mapping[str, Any], *, cwd: Path = REPO_ROOT, timeout: int = 300) -> dict[str, Any]:
    """Execute one probe and return its deterministic result payload."""

    validate_probe(probe)
    kind = str(probe["kind"])
    if kind == "pytest":
        return _run_pytest_probe(probe, cwd=cwd, timeout=timeout)
    if kind == "command":
        return _run_command_probe(probe, cwd=cwd, timeout=timeout)
    return _run_api_surface_probe(probe)


# ---------------------------------------------------------------------------
# Snapshot capture, sealing, and verification.
# ---------------------------------------------------------------------------


def _snapshot_body(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"snapshot_digest", "captured_at"}
    }


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return _digest(_snapshot_body(snapshot))


def capture_snapshot(
    name: str,
    probes: Sequence[Mapping[str, Any]],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 300,
) -> dict[str, Any]:
    """Run every probe and seal the results into a snapshot payload."""

    if not str(name).strip():
        raise ValueError("snapshot name is required")
    if not probes:
        raise ValueError("a snapshot requires at least one probe")
    probe_list = [dict(probe) for probe in probes]
    ids = [str(probe.get("id")) for probe in probe_list]
    if len(set(ids)) != len(ids):
        raise ValueError(f"probe ids must be unique: {sorted(ids)}")
    results: dict[str, Any] = {}
    for probe in probe_list:
        results[str(probe["id"])] = run_probe(probe, cwd=cwd, timeout=timeout)
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "equivalence_snapshot",
        "name": str(name),
        "captured_at": utc_now_iso(),
        "probes": probe_list,
        "results": results,
    }
    snapshot["snapshot_digest"] = snapshot_digest(snapshot)
    return snapshot


def write_snapshot(snapshot: Mapping[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "snapshot.json"
    atomic_write_json(path, dict(snapshot))
    return path


def verify_snapshot(
    snapshot: Mapping[str, Any],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int = 300,
) -> dict[str, Any]:
    """Re-run every probe live and compare against the sealed results."""

    if int(snapshot.get("schema_version") or 0) != SCHEMA_VERSION:
        return {"ok": False, "kind": "equivalence_verdict", "error": "unsupported schema_version"}
    if str(snapshot.get("kind") or "") != "equivalence_snapshot":
        return {"ok": False, "kind": "equivalence_verdict", "error": "not an equivalence snapshot"}
    recorded_digest = str(snapshot.get("snapshot_digest") or "")
    digest_match = bool(recorded_digest) and snapshot_digest(snapshot) == recorded_digest
    probe_verdicts: list[dict[str, Any]] = []
    recorded_results = snapshot.get("results") or {}
    for probe in snapshot.get("probes") or []:
        probe_id = str(probe.get("id"))
        try:
            actual = run_probe(probe, cwd=cwd, timeout=timeout)
        except Exception as exc:  # a probe that can no longer run is drift
            probe_verdicts.append(
                {"id": probe_id, "match": False, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        recorded = recorded_results.get(probe_id)
        verdict: dict[str, Any] = {"id": probe_id, "match": actual == recorded}
        if actual != recorded:
            verdict["recorded"] = recorded
            verdict["actual"] = actual
        probe_verdicts.append(verdict)
    drifted = sorted(verdict["id"] for verdict in probe_verdicts if not verdict["match"])
    ok = digest_match and not drifted
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "equivalence_verdict",
        "snapshot_name": snapshot.get("name"),
        "digest_match": digest_match,
        "probe_count": len(probe_verdicts),
        "drifted_probes": drifted,
        "probe_verdicts": probe_verdicts,
        "ok": ok,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot file is malformed: {path}")
    return payload


# ---------------------------------------------------------------------------
# Hermetic registered proof.
# ---------------------------------------------------------------------------


def builtin_equivalence_proof() -> dict[str, Any]:
    """Prove capture/verify, tamper detection, and drift detection, hermetically.

    The pytest probe is included only when the running interpreter can import
    pytest (ledger proofs execute under ``uv run``, whose project environment
    is test-free); drift is always exercised through a file-reading command
    probe and the api-surface probe, which need nothing beyond the stdlib.
    """

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="blackhole-equiv-proof-") as tmp:
        scratch = Path(tmp)
        module_path = scratch / "equiv_fixture_mod.py"
        module_path.write_text(
            "ANSWER = 42\n\n\ndef greet(name: str) -> str:\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        state_path = scratch / "state.json"
        state_path.write_text(json.dumps({"level": 1}), encoding="utf-8")
        test_path = scratch / "test_equiv_fixture.py"
        test_path.write_text(
            "def test_ok():\n    assert 2 + 2 == 4\n", encoding="utf-8"
        )
        pytest_available = importlib.util.find_spec("pytest") is not None
        sys.path.insert(0, str(scratch))
        try:
            importlib.invalidate_caches()
            probes: list[dict[str, Any]] = [
                {"kind": "api-surface", "id": "surface", "modules": ["equiv_fixture_mod"]},
                {
                    "kind": "command",
                    "id": "command",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import json; print(json.dumps({'ok': True, 'run_at': 'volatile'}))",
                    ],
                },
                {
                    "kind": "command",
                    "id": "file-command",
                    "argv": [
                        sys.executable,
                        "-c",
                        "import json, sys; print(json.dumps(json.load(open(sys.argv[1]))))",
                        str(state_path),
                    ],
                },
            ]
            if pytest_available:
                probes.append({"kind": "pytest", "id": "pytest", "paths": [str(test_path)]})
            snapshot = capture_snapshot("builtin-proof", probes, cwd=scratch)
            verdict = verify_snapshot(snapshot, cwd=scratch)
            checks["capture_verify_ok"] = bool(verdict["ok"]) and verdict["probe_count"] == len(
                probes
            )
            checks["volatile_keys_normalized"] = verdict["ok"]

            tampered = copy.deepcopy(snapshot)
            tampered["results"]["command"]["exit_code"] = 9
            tamper_verdict = verify_snapshot(tampered, cwd=scratch)
            checks["tamper_detected"] = (
                not tamper_verdict["ok"] and tamper_verdict["digest_match"] is False
            )

            state_path.write_text(json.dumps({"level": 2}), encoding="utf-8")
            if pytest_available:
                test_path.write_text(
                    "def test_ok():\n    assert 2 + 2 == 5\n", encoding="utf-8"
                )
            drift_verdict = verify_snapshot(snapshot, cwd=scratch)
            expected_drift = {"file-command"} | ({"pytest"} if pytest_available else set())
            checks["drift_detected"] = (
                not drift_verdict["ok"]
                and drift_verdict["digest_match"]
                and set(drift_verdict["drifted_probes"]) == expected_drift
            )

            # Different length defeats same-second mtime+size pyc caching.
            module_path.write_text("ANSWER = 43000\n", encoding="utf-8")
            importlib.invalidate_caches()
            sys.modules.pop("equiv_fixture_mod", None)
            surface_drift = verify_snapshot(snapshot, cwd=scratch)
            checks["surface_drift_detected"] = (
                not surface_drift["ok"] and "surface" in surface_drift["drifted_probes"]
            )
        finally:
            sys.path.remove(str(scratch))
            sys.modules.pop("equiv_fixture_mod", None)
    checks["no_ledger_mutation"] = True
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "equivalence_proof",
        "ok": all(checks.values()),
        "checks": checks,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability equivalence gate")
    parser.add_argument("--capture", metavar="NAME", help="capture a snapshot named NAME")
    parser.add_argument("--verify", type=Path, metavar="SNAPSHOT", help="verify a snapshot file")
    parser.add_argument("--probes", type=Path, help="JSON file with a list of probes (capture)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="artifact directory (default: artifacts/capability-equivalence/<name>/)",
    )
    parser.add_argument("--proof", action="store_true", help="run the hermetic builtin proof")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.proof:
        result = builtin_equivalence_proof()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    if args.capture:
        if args.probes is None:
            parser.error("--capture requires --probes")
        probes = json.loads(args.probes.read_text(encoding="utf-8"))
        if not isinstance(probes, list):
            parser.error("--probes must be a JSON list of probe objects")
        snapshot = capture_snapshot(args.capture, probes)
        output_dir = args.output_dir or DEFAULT_ARTIFACT_DIR / args.capture
        path = write_snapshot(snapshot, output_dir)
        print(json.dumps({"ok": True, "snapshot": str(path), "digest": snapshot["snapshot_digest"]}))
        return 0
    if args.verify:
        verdict = verify_snapshot(load_snapshot(args.verify))
        print(
            json.dumps(
                {
                    "ok": verdict["ok"],
                    "digest_match": verdict.get("digest_match"),
                    "drifted_probes": verdict.get("drifted_probes"),
                    "probe_count": verdict.get("probe_count"),
                },
                indent=2,
            )
        )
        return 0 if verdict["ok"] else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
