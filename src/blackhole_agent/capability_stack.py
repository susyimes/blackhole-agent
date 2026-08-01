"""Goal-stack health: the whole goal-directed stack as one invocable proof.

The mission built a stack of planes — application (goals solved by BFS
planning), recovery (blocked goals healed), fragility (reliability measured),
watchdog (drift gated) — each with its own proof. This module compounds them
into a single health surface:

- runs every plane's live pass and records only the headline fields
  (score, healthy counts, drift, fragility, recovery) — the stack is
  healthy only when ALL of them are green at once;
- digest-sealed summary under ``artifacts/capability-stack/`` whose
  verification recomputes the health derivation from the recorded
  headlines — a summary that reports health while one plane is red fails
  verification;
- a registered proof (:func:`builtin_stack_health`) that proves the full
  stack is green and falsifies a tampered headline.

This is deliberately a composition surface, not a fifth plane: no new
behavior lives here beyond the honest aggregation of the planes' own
live passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_application import run_application_plane
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.capability_fragility import run_fragility_audit
from blackhole_agent.capability_recovery import run_recovery_loop
from blackhole_agent.capability_watchdog import run_goal_watchdog

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-stack"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-stack.json"


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def compute_stack_health(headlines: Mapping[str, Any]) -> dict[str, Any]:
    """Pure stack-health derivation from recorded plane headlines.

    The stack is healthy only when every plane's headline is green: all
    goals plan-attributed, zero drift, fragility measured with its robust
    goal intact, and a zero-repair recovery baseline. This function is the
    single grading rule: a summary whose recorded health disagrees with its
    recorded headlines is misgraded and fails verification.
    """

    application = headlines.get("application") or {}
    watchdog = headlines.get("watchdog") or {}
    fragility = headlines.get("fragility") or {}
    recovery = headlines.get("recovery") or {}
    planes_green = {
        "application": bool(
            application.get("application_score") == 1.0 and application.get("unsolvable_count") == 0
        ),
        "watchdog": bool(watchdog.get("drifted_goals") == [] and watchdog.get("ok") is True),
        "fragility": bool(
            fragility.get("fragility_score") is not None
            and "ledger-inventory-check" in (fragility.get("robust_goals") or [])
        ),
        "recovery": bool(recovery.get("ok") is True and recovery.get("repair_count") == 0),
    }
    return {
        "planes_green": planes_green,
        "green_count": sum(1 for green in planes_green.values() if green),
        "plane_count": len(planes_green),
        "healthy": all(planes_green.values()),
    }


def run_stack_health() -> dict[str, Any]:
    """Run every goal-stack plane live and seal the composite headline."""

    application = run_application_plane()
    watchdog = run_goal_watchdog()
    fragility = run_fragility_audit()
    recovery = run_recovery_loop()

    headlines = {
        "application": {
            "application_score": application["application"]["application_score"],
            "task_count": application["application"]["task_count"],
            "unsolvable_count": application["application"]["unsolvable_count"],
            "ok": bool(application["ok"]),
        },
        "watchdog": {
            "ok": bool(watchdog["ok"]),
            "healthy_count": watchdog["healthy_count"],
            "goal_count": watchdog["goal_count"],
            "drifted_goals": list(watchdog["drifted_goals"]),
        },
        "fragility": {
            "fragility_score": fragility["fragility"]["fragility_score"],
            "robust_goals": list(fragility["fragility"]["robust_goals"]),
            "max_blast_radius": fragility["fragility"]["max_blast_radius"],
            "max_redundancy_depth": fragility["fragility"].get("max_redundancy_depth"),
        },
        "recovery": {
            "ok": bool(recovery["ok"]),
            "repair_count": recovery["recovery"]["repair_count"],
            "task_pass_count": recovery["recovery"]["task_pass_count"],
            "task_count": recovery["recovery"]["task_count"],
        },
    }
    health = compute_stack_health(headlines)
    headlines_digest = _digest(headlines)
    health_digest = _digest(health)
    report_digest = hashlib.sha256(
        f"stack:{headlines_digest}:{health_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_stack_health",
        "run_at": utc_now_iso(),
        "headlines": headlines,
        "health": health,
        "headlines_digest": headlines_digest,
        "health_digest": health_digest,
        "report_digest": report_digest,
        "ok": health["healthy"],
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_stack_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the stack-health report artifact and refresh the latest pointer."""

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
        "healthy": (report.get("health") or {}).get("healthy"),
    }


def verify_stack_report(report_dir: Path) -> dict[str, Any]:
    """Recompute health from recorded headlines and re-check the digest chain.

    Verification is pure: it never re-runs a plane. A summary whose
    headlines were edited, whose health was rounded up, or whose digest
    chain was tampered with fails verification.
    """

    report_path = report_dir / "report.json"
    if not report_path.exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    headlines = report.get("headlines") or {}

    recomputed = compute_stack_health(headlines)
    headlines_digest = _digest(headlines)
    health_digest = _digest(recomputed)
    report_digest = hashlib.sha256(
        f"stack:{headlines_digest}:{health_digest}".encode("utf-8")
    ).hexdigest()
    checks = {
        "headlines_digest": headlines_digest == report.get("headlines_digest"),
        "health_recomputed_matches": recomputed == report.get("health"),
        "health_digest": health_digest == report.get("health_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        "ok_matches_health": bool(report.get("ok")) == recomputed["healthy"],
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_stack_health() -> dict[str, Any]:
    """Registered proof for ``capability.goal-stack-health``.

    Proves the whole goal-directed stack is green in one pass, then
    falsifies: a tampered headline (one plane flipped red with digests
    re-sealed) must fail verification because the recomputed health
    disagrees, and a rounded-up health flag must fail as misgrade.
    """

    import os
    import tempfile

    report = run_stack_health()
    if not report["ok"]:
        return {"ok": False, "stage": "stack", "health": report["health"]}

    report_dir_raw = (os.environ.get("BLACKHOLE_STACK_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_stack_report(report, out)
        verified = verify_stack_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": not report["used_skill_route_discovery"],
            "health": report["health"],
            "report_digest": report["report_digest"],
            "report_dir": str(out),
            "used_skill_route_discovery": report["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-stack-proof-") as tmp:
        out = Path(tmp) / "report"
        write_stack_report(report, out)
        verified = verify_stack_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one plane's headline red, re-seal every
        # digest — the recomputed health must disagree with the recorded one.
        tampered = json.loads(json.dumps(report))
        tampered["headlines"]["watchdog"]["drifted_goals"] = ["routed-triage-record"]
        tampered["headlines"]["watchdog"]["ok"] = False
        tampered["headlines_digest"] = _digest(tampered["headlines"])
        atomic_write_json(out / "report.json", tampered)
        if verify_stack_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "tampered headline passed verification"}

        # Falsifiability 2: round the health flag up without touching headlines.
        rounded = json.loads(json.dumps(report))
        rounded["health"]["healthy"] = False
        rounded["ok"] = True
        atomic_write_json(out / "report.json", rounded)
        if verify_stack_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "rounded health passed verification"}

    return {
        "ok": not report["used_skill_route_discovery"],
        "health": report["health"],
        "report_digest": report["report_digest"],
        "tamper_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Goal-stack health")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the stack health pass and seal a report")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_stack_health()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_stack_report(report, out)
        summary["health"] = report["health"]
    else:
        summary = verify_stack_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
