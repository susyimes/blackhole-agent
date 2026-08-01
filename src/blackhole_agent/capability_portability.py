"""Portability proof: the goal stack must work on a pristine checkout.

Every plane in this repository proves itself in *this* checkout. That leaves
a quiet assumption untested: the goal-directed stack (application plane,
watchdog, oracles, fixtures, ledger) works anywhere, not just here — no
hidden dependency on this worktree's absolute paths, accumulated artifacts,
or environment. This module proves it directly:

- ``checkout_pristine_source`` materializes a pristine checkout of the
  tracked source (``git archive HEAD`` — src, tests, capabilities,
  schemas, pyproject) into a temp directory; nothing from this worktree's
  filesystem leaks in except tracked content;
- the goal watchdog and the application plane run **in that checkout**
  (``PYTHONPATH=<checkout>/src``), so imports, the ledger, fixtures, and
  report artifacts all resolve against the pristine tree;
- determinism is proven *across checkouts*: two independent pristine
  checkouts must produce identical watchdog and application digests;
- falsification: a pristine checkout whose ledger stamps
  ``domain.tool-routing`` red must flag ``routed-triage-record`` as drift —
  portability failures are reported, never rounded up;
- a digest-sealed report under ``artifacts/capability-portability/`` whose
  verification recomputes the grade and digest chain from the recorded
  checkout summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-portability"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-portability.json"

ARCHIVE_PATHS = ("src", "tests", "capabilities", "schemas", "pyproject.toml")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def checkout_pristine_source(dest: Path) -> dict[str, Any]:
    """Materialize the tracked source of HEAD into ``dest`` via git archive."""

    archive = subprocess.run(
        ["git", "archive", "HEAD", *ARCHIVE_PATHS],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=True,
    )
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["tar", "-x", "-C", str(dest)],
        input=archive.stdout,
        capture_output=True,
        check=True,
    )
    file_count = sum(1 for path in dest.rglob("*") if path.is_file())
    return {"dest": str(dest), "file_count": file_count}


def _run_module(checkout: Path, module: str) -> dict[str, Any]:
    """Run ``python -m <module> --run`` against a pristine checkout."""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(checkout / "src")
    completed = subprocess.run(
        [sys.executable, "-m", module, "--run"],
        cwd=str(checkout),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    stdout = (completed.stdout or "").strip()
    summary: dict[str, Any] = {}
    if stdout:
        try:
            summary = json.loads(stdout)
        except ValueError:
            try:
                summary = json.loads(stdout.splitlines()[-1])
            except ValueError:
                summary = {}
    return {"exit_code": completed.returncode, "summary": summary, "stderr_tail": (completed.stderr or "")[-300:]}


def _watchdog_summary(checkout: Path) -> dict[str, Any]:
    result = _run_module(checkout, "blackhole_agent.capability_watchdog")
    summary = result["summary"]
    return {
        "exit_code": result["exit_code"],
        "ok": bool(summary.get("ok")),
        "healthy_count": summary.get("healthy_count"),
        "goal_count": summary.get("goal_count"),
        "drifted_goals": sorted(summary.get("drifted_goals") or []),
        "report_digest": summary.get("report_digest"),
    }


def _application_summary(checkout: Path) -> dict[str, Any]:
    result = _run_module(checkout, "blackhole_agent.capability_application")
    summary = result["summary"]
    grade = summary.get("application") or {}
    return {
        "exit_code": result["exit_code"],
        "ok": bool(summary.get("ok")),
        "application_score": grade.get("application_score"),
        "task_count": grade.get("task_count"),
        "unsolvable_count": grade.get("unsolvable_count"),
    }


def _stamp_capability_red(checkout: Path, capability_id: str) -> None:
    ledger_path = checkout / "capabilities" / "ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["capabilities"][capability_id]["last_proof_exit_code"] = 1
    payload["capabilities"][capability_id]["last_proved_at"] = ""
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_portability_plane() -> dict[str, Any]:
    """Prove the goal stack on pristine checkouts, plus a corrupted one."""

    with tempfile.TemporaryDirectory(prefix="capability-portability-") as tmp:
        base = Path(tmp)
        checkout_a = base / "checkout-a"
        checkout_b = base / "checkout-b"
        checkout_c = base / "checkout-c"

        archive_a = checkout_pristine_source(checkout_a)
        watchdog_a = _watchdog_summary(checkout_a)
        application_a = _application_summary(checkout_a)

        checkout_pristine_source(checkout_b)
        watchdog_b = _watchdog_summary(checkout_b)
        application_b = _application_summary(checkout_b)

        checkout_pristine_source(checkout_c)
        _stamp_capability_red(checkout_c, "domain.tool-routing")
        watchdog_c = _watchdog_summary(checkout_c)

    pristine_ok = (
        watchdog_a["ok"]
        and watchdog_a["healthy_count"] == watchdog_a["goal_count"]
        and application_a["ok"]
        and application_a["application_score"] == 1.0
        and application_a["unsolvable_count"] == 0
    )
    cross_checkout_determinism = (
        watchdog_a["report_digest"] == watchdog_b["report_digest"]
        and application_a["application_score"] == application_b["application_score"]
    )
    corruption_detected = (
        not watchdog_c["ok"]
        and watchdog_c["exit_code"] != 0
        and watchdog_c["drifted_goals"] == ["routed-triage-record"]
    )

    checkouts = {
        "pristine_a": {"archive": archive_a, "watchdog": watchdog_a, "application": application_a},
        "pristine_b": {"watchdog": watchdog_b, "application": application_b},
        "corrupted": {"watchdog": watchdog_c},
    }
    grade = {
        "pristine_ok": pristine_ok,
        "cross_checkout_determinism": cross_checkout_determinism,
        "corruption_detected": corruption_detected,
        "goal_count": watchdog_a["goal_count"],
        "application_score": application_a["application_score"],
    }
    checkouts_digest = _digest(checkouts)
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"portability:{checkouts_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_portability_plane",
        "run_at": utc_now_iso(),
        "checkouts": checkouts,
        "portability": grade,
        "checkouts_digest": checkouts_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": pristine_ok and cross_checkout_determinism and corruption_detected,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_portability_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the portability report artifact and refresh the latest pointer."""

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "report.json", dict(report))
    if output_dir.parent == LATEST_POINTER.parent:
        atomic_write_json(
            LATEST_POINTER,
            {"report_dir": output_dir.name, "report_digest": report.get("report_digest")},
        )
    return {
        "ok": bool(report.get("ok")),
        "output_dir": str(output_dir),
        "report_digest": report.get("report_digest"),
        "portability": dict(report.get("portability") or {}),
    }


def verify_portability_report(report_dir: Path) -> dict[str, Any]:
    """Recompute the grade and digest chain from recorded checkout summaries.

    Verification is pure: it never re-materializes a checkout. A report
    whose grade was rounded up, whose checkout summaries were edited, or
    whose digest chain was tampered with fails verification.
    """

    report_path = report_dir / "report.json"
    if not report_path.exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    checkouts = report.get("checkouts") or {}

    pristine = checkouts.get("pristine_a") or {}
    pristine_b = checkouts.get("pristine_b") or {}
    corrupted = checkouts.get("corrupted") or {}
    watchdog_a = pristine.get("watchdog") or {}
    application_a = pristine.get("application") or {}
    watchdog_b = pristine_b.get("watchdog") or {}
    application_b = pristine_b.get("application") or {}
    watchdog_c = corrupted.get("watchdog") or {}

    regraded = {
        "pristine_ok": bool(
            watchdog_a.get("ok")
            and watchdog_a.get("healthy_count") == watchdog_a.get("goal_count")
            and application_a.get("ok")
            and application_a.get("application_score") == 1.0
            and application_a.get("unsolvable_count") == 0
        ),
        "cross_checkout_determinism": bool(
            watchdog_a.get("report_digest")
            and watchdog_a.get("report_digest") == watchdog_b.get("report_digest")
            and application_a.get("application_score") == application_b.get("application_score")
        ),
        "corruption_detected": bool(
            not watchdog_c.get("ok", True)
            and watchdog_c.get("exit_code") != 0
            and watchdog_c.get("drifted_goals") == ["routed-triage-record"]
        ),
        "goal_count": watchdog_a.get("goal_count"),
        "application_score": application_a.get("application_score"),
    }
    checkouts_digest = _digest(checkouts)
    grade_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"portability:{checkouts_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    checks = {
        "checkouts_digest": checkouts_digest == report.get("checkouts_digest"),
        "grade_recomputed_matches": regraded == report.get("portability"),
        "grade_digest": grade_digest == report.get("grade_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        "ok_matches_grade": bool(report.get("ok"))
        == (regraded["pristine_ok"] and regraded["cross_checkout_determinism"] and regraded["corruption_detected"]),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_portability_plane() -> dict[str, Any]:
    """Registered proof for ``capability.portability-proof``.

    Runs the plane (three pristine checkouts: two healthy + one corrupted),
    seals and verifies the report, then falsifies two ways: a tampered
    checkout summary and a rounded-up grade must fail verification.
    """

    import tempfile as _tempfile

    report = run_portability_plane()
    if not report["ok"]:
        return {"ok": False, "stage": "plane", "portability": report["portability"]}

    report_dir_raw = (os.environ.get("BLACKHOLE_PORTABILITY_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_portability_report(report, out)
        verified = verify_portability_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": not report["used_skill_route_discovery"],
            "portability": report["portability"],
            "report_digest": report["report_digest"],
            "report_dir": str(out),
            "used_skill_route_discovery": report["used_skill_route_discovery"],
        }

    with _tempfile.TemporaryDirectory(prefix="capability-portability-proof-") as tmp:
        out = Path(tmp) / "report"
        write_portability_report(report, out)
        verified = verify_portability_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: edit a recorded checkout summary; verification must fail.
        tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
        tampered["checkouts"]["corrupted"]["watchdog"]["drifted_goals"] = []
        atomic_write_json(out / "report.json", tampered)
        if verify_portability_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "edited summary passed verification"}

        # Falsifiability 2: round the grade up without touching summaries.
        rounded = json.loads(json.dumps(report))
        rounded["portability"]["corruption_detected"] = False
        rounded["ok"] = True
        atomic_write_json(out / "report.json", rounded)
        if verify_portability_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "rounded grade passed verification"}

    return {
        "ok": not report["used_skill_route_discovery"],
        "portability": report["portability"],
        "report_digest": report["report_digest"],
        "tamper_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability portability proof")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the plane and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_portability_plane()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_portability_report(report, out)
    else:
        summary = verify_portability_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
