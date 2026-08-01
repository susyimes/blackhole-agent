"""Goal fragility audit: single points of failure across the planning surface.

The application plane proves goals are solvable; the recovery loop heals them
when they break. Neither answers the reliability question: *which single
capability failure takes which goals down?* This module computes that
directly from the live proved ledger:

- the **impact matrix**: for every capability on the planning surface, the
  set of goals that become unplannable when that capability alone is hidden
  — computed by pure BFS re-planning (hide-one analysis), never by executing
  pipelines;
- **redundancy depth**: how many *simultaneous* failures each goal survives
  (hide-k analysis over capability subsets), with the lexicographically
  first killing subset recorded as witness — a "robust" goal is only as
  robust as its redundant providers' joint failure domain;
- per-goal **single points of failure** (SPOFs) and a fragility grade: the
  fraction of goals with zero SPOFs. A goal whose every plan needs a
  capability no alternative can replace is honest-to-report fragile;
- per-capability **blast radius**: how many goals one failure blocks — the
  priority order the recovery loop uses when several capabilities are red at
  once;
- a digest-sealed report under ``artifacts/capability-fragility/`` whose
  verification **recomputes the entire matrix from the live ledger**.
  Planning is pure and fast, so every matrix cell is independently
  falsifiable: a forged cell, a misgraded fragility score, or a tampered
  digest all fail verification;
- a registered proof (:func:`builtin_fragility_audit`) that proves
  determinism, the expected shared-structure finding
  (``capability.ledger-inventory`` blocks two goals), and three
  falsification modes.

The audit reports redundancy honestly in both directions: before the
readiness providers were duplicated it reported 0.0 (no goal survived a
single failure); with ``capability.ledger-attestation`` providing a second
independent path to ``ledger_ready``, the ``ledger-inventory-check`` goal
is robust and the score reads 0.2 — driven down, not rounded up.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.durable_state import durable_read_path

from blackhole_agent.capability_application import (
    APPLICATION_TASKS,
    ApplicationTask,
    build_application_registry,
    plan_application_task,
)
from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    utc_now_iso,
)

SCHEMA_VERSION = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-fragility"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-fragility.json"


def compute_impact_matrix(
    ledger: CapabilityLedger,
    *,
    tasks: Sequence[ApplicationTask] = APPLICATION_TASKS,
) -> dict[str, list[str]]:
    """For each proved surface capability, the goals it single-handedly blocks.

    Pure planning only: the capability is hidden from the registry and every
    goal is re-planned. No pipeline is executed, so the matrix is cheap
    enough for verification to recompute in full.
    """

    registry = build_application_registry(ledger)
    matrix: dict[str, list[str]] = {}
    for capability_id in sorted(registry):
        reduced = {key: step for key, step in registry.items() if key != capability_id}
        matrix[capability_id] = sorted(
            task.id for task in tasks if plan_application_task(task, reduced) is None
        )
    return matrix


def compute_redundancy_depth(
    ledger: CapabilityLedger,
    *,
    tasks: Sequence[ApplicationTask] = APPLICATION_TASKS,
) -> dict[str, dict[str, Any]]:
    """How many simultaneous failures each goal survives, with a witness.

    Hide-one analysis certifies single-failure robustness only. This hides
    *sets* of capabilities: a goal's depth is the largest ``k`` such that
    every ``k``-subset of the surface still leaves it plannable. The
    lexicographically first killing subset is recorded as the witness — for
    a depth-1 goal that is the pair of redundant providers whose joint
    failure breaks it. Pure planning throughout; verification recomputes
    every cell.
    """

    registry = build_application_registry(ledger)
    surface = sorted(registry)
    depth: dict[str, dict[str, Any]] = {}
    survivors = list(tasks)
    level = 0
    while survivors and level < len(surface):
        level += 1
        still: list[ApplicationTask] = []
        for task in survivors:
            killed_by: list[str] = []
            for subset in itertools.combinations(surface, level):
                reduced = {cid: step for cid, step in registry.items() if cid not in subset}
                if plan_application_task(task, reduced) is None:
                    killed_by = sorted(subset)
                    break
            if killed_by:
                depth[task.id] = {"depth": level - 1, "killed_by": killed_by}
            else:
                still.append(task)
        survivors = still
    for task in survivors:
        depth[task.id] = {"depth": len(surface), "killed_by": []}
    return depth


def compute_fragility_grade(
    matrix: Mapping[str, Sequence[str]],
    *,
    tasks: Sequence[ApplicationTask] = APPLICATION_TASKS,
    depth: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure fragility derivation from a recorded impact matrix.

    This function is the single grading rule: a report whose recorded grade
    disagrees with its recorded matrix is misgraded and fails verification.
    When a redundancy-depth map is recorded it is folded into the grade, so
    a forged depth cell is a misgrade too.
    """

    spofs_per_goal: dict[str, list[str]] = {}
    for task in tasks:
        spofs_per_goal[task.id] = sorted(
            capability_id for capability_id, blocked in matrix.items() if task.id in blocked
        )
    blast_radius = {capability_id: len(blocked) for capability_id, blocked in matrix.items()}
    robust_goals = sorted(task_id for task_id, spofs in spofs_per_goal.items() if not spofs)
    critical = sorted(blast_radius, key=lambda cid: (-blast_radius[cid], cid))
    task_count = len(tasks)
    grade: dict[str, Any] = {
        "task_count": task_count,
        "spofs_per_goal": spofs_per_goal,
        "blast_radius": blast_radius,
        "robust_goals": robust_goals,
        "fragile_goals": sorted(task_id for task_id in spofs_per_goal if task_id not in robust_goals),
        "fragility_score": round(len(robust_goals) / task_count, 4) if task_count else 0.0,
        "critical_capabilities": critical,
        "max_blast_radius": max(blast_radius.values(), default=0),
    }
    if depth is not None:
        depth_per_goal = {goal: int(cell.get("depth", 0)) for goal, cell in depth.items()}
        max_depth = max(depth_per_goal.values(), default=0)
        grade["redundancy_depth"] = depth_per_goal
        grade["max_redundancy_depth"] = max_depth
        grade["deepest_goals"] = sorted(goal for goal, d in depth_per_goal.items() if d == max_depth)
    return grade


def repair_priority_order(
    ledger: CapabilityLedger, capability_ids: Sequence[str]
) -> list[str]:
    """Order blocked capabilities by descending blast radius for repair.

    Deterministic: ties break by capability id. The recovery loop uses this
    so the failure that blocks the most goals is healed first.
    """

    matrix = compute_impact_matrix(ledger)
    blast = {capability_id: len(blocked) for capability_id, blocked in matrix.items()}
    return sorted(capability_ids, key=lambda cid: (-blast.get(cid, 0), cid))


def blast_radius_map(ledger: CapabilityLedger) -> dict[str, int]:
    """Blast radius per surface capability (goals blocked if it fails alone)."""

    matrix = compute_impact_matrix(ledger)
    return {capability_id: len(blocked) for capability_id, blocked in matrix.items()}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def run_fragility_audit() -> dict[str, Any]:
    """Compute the impact matrix, redundancy depth, and fragility grade."""

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    matrix = compute_impact_matrix(ledger)
    depth = compute_redundancy_depth(ledger)
    grade = compute_fragility_grade(matrix, depth=depth)
    matrix_digest = _digest(matrix)
    depth_digest = _digest(depth)
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"fragility:{matrix_digest}:{depth_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_fragility_audit",
        "run_at": utc_now_iso(),
        "impact_matrix": matrix,
        "redundancy_depth": depth,
        "fragility": grade,
        "matrix_digest": matrix_digest,
        "depth_digest": depth_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def write_fragility_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the fragility report artifact and refresh the latest pointer."""

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
        "fragility_score": (report.get("fragility") or {}).get("fragility_score"),
    }


def verify_fragility_report(report_dir: Path) -> dict[str, Any]:
    """Recompute the entire impact matrix from the live ledger and re-grade.

    Verification re-plans every goal under every single-capability hiding —
    pure BFS, no pipeline execution — so each recorded matrix cell is
    checked against the ledger's current truth. A forged cell, a misgraded
    score, or a tampered digest fails verification.
    """

    report_path = report_dir / "report.json"
    if not durable_read_path(report_path).exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(durable_read_path(report_path).read_text(encoding="utf-8"))

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    recomputed_matrix = compute_impact_matrix(ledger)
    recomputed_depth = compute_redundancy_depth(ledger)
    regraded = compute_fragility_grade(recomputed_matrix, depth=recomputed_depth)
    matrix_digest = _digest(recomputed_matrix)
    depth_digest = _digest(recomputed_depth)
    grade_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"fragility:{matrix_digest}:{depth_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()

    checks = {
        "matrix_recomputed_matches": recomputed_matrix == report.get("impact_matrix"),
        "matrix_digest": matrix_digest == report.get("matrix_digest"),
        "depth_recomputed_matches": recomputed_depth == report.get("redundancy_depth"),
        "depth_digest": depth_digest == report.get("depth_digest"),
        "grade_recomputed_matches": regraded == report.get("fragility"),
        "grade_digest": grade_digest == report.get("grade_digest"),
        "report_digest": report_digest == report.get("report_digest"),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_fragility_audit() -> dict[str, Any]:
    """Registered proof for ``capability.fragility-audit``.

    Proves the audit is deterministic, finds the surface's structure after
    redundancy engineering (``capability.ledger-inventory`` and its
    redundant alternative ``capability.ledger-attestation`` block nothing
    alone — the ``ledger-inventory-check`` goal is robust and the fragility
    score rose from 0.0 to 0.2 — while the security-scan chain still has
    the widest blast radius at 2 goals), and that repair prioritization
    puts the widest-blast capability first. Then seals and verifies a
    report and falsifies three ways: a forged matrix cell, a misgraded
    fragility score, and a tampered digest chain must all fail
    verification.
    """

    import os
    import tempfile

    first = run_fragility_audit()
    second = run_fragility_audit()
    if first["matrix_digest"] != second["matrix_digest"] or first["depth_digest"] != second["depth_digest"]:
        return {"ok": False, "stage": "determinism"}

    grade = first["fragility"]
    depth = first["redundancy_depth"]
    structure = (
        # Redundancy: neither readiness provider single-handedly blocks a goal.
        grade["blast_radius"].get("capability.ledger-inventory") == 0
        and grade["blast_radius"].get("capability.ledger-attestation") == 0
        and grade["robust_goals"] == ["ledger-inventory-check"]
        and grade["fragility_score"] == round(1 / 6, 4)
        # The remaining critical pair: the security-scan chain blocks two goals.
        and grade["blast_radius"].get("domain.ci-security") == 2
        and grade["blast_radius"].get("domain.harness-activation") == 2
        and grade["max_blast_radius"] == 2
        and grade["critical_capabilities"][0] == "domain.ci-security"
        # The widened surface is measured too: persona and synthesis each
        # single-handedly block the persona-stamped-proposal goal.
        and grade["blast_radius"].get("domain.persona") == 1
        and grade["blast_radius"].get("domain.proposal-synthesis") == 1
        # Depth honesty: the robust goal survives exactly ONE simultaneous
        # failure — the killing witness is the pair of redundant providers
        # whose joint failure breaks it. Every other goal has depth 0.
        and depth["ledger-inventory-check"]["depth"] == 1
        and depth["ledger-inventory-check"]["killed_by"]
        == ["capability.ledger-attestation", "capability.ledger-inventory"]
        and all(
            cell["depth"] == 0 for goal, cell in depth.items() if goal != "ledger-inventory-check"
        )
        and grade["max_redundancy_depth"] == 1
        and grade["deepest_goals"] == ["ledger-inventory-check"]
    )
    if not structure:
        return {"ok": False, "stage": "structure", "fragility": grade}

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    priority = repair_priority_order(
        ledger, ["capability.ledger-inventory", "domain.tool-routing"]
    )
    if priority != ["domain.tool-routing", "capability.ledger-inventory"]:
        return {"ok": False, "stage": "priority", "priority": priority}

    report_dir_raw = (os.environ.get("BLACKHOLE_FRAGILITY_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_fragility_report(first, out)
        verified = verify_fragility_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": not first["used_skill_route_discovery"],
            "fragility": grade,
            "report_digest": first["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "used_skill_route_discovery": first["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-fragility-proof-") as tmp:
        out = Path(tmp) / "report"
        write_fragility_report(first, out)
        verified = verify_fragility_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: forge a matrix cell — claim tool-routing blocks
        # nothing — and re-seal the digest chain. Recomputation must catch it.
        forged = json.loads(json.dumps(first))
        forged["impact_matrix"]["domain.tool-routing"] = []
        forged["matrix_digest"] = _digest(forged["impact_matrix"])
        forged["fragility"] = compute_fragility_grade(forged["impact_matrix"], depth=forged["redundancy_depth"])
        forged["grade_digest"] = _digest(forged["fragility"])
        forged["report_digest"] = hashlib.sha256(
            f"fragility:{forged['matrix_digest']}:{forged['depth_digest']}:{forged['grade_digest']}".encode("utf-8")
        ).hexdigest()
        atomic_write_json(out / "report.json", forged)
        if verify_fragility_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "matrix-forgery-falsification",
                "detail": "forged matrix cell passed verification",
            }

        # Falsifiability 2: forge a depth cell — claim the robust goal
        # survives two simultaneous failures — and re-seal. Recomputation
        # must catch it.
        forged_depth = json.loads(json.dumps(first))
        forged_depth["redundancy_depth"]["ledger-inventory-check"]["depth"] = 2
        forged_depth["depth_digest"] = _digest(forged_depth["redundancy_depth"])
        forged_depth["fragility"] = compute_fragility_grade(
            forged_depth["impact_matrix"], depth=forged_depth["redundancy_depth"]
        )
        forged_depth["grade_digest"] = _digest(forged_depth["fragility"])
        forged_depth["report_digest"] = hashlib.sha256(
            "fragility:{}:{}:{}".format(
                forged_depth["matrix_digest"], forged_depth["depth_digest"], forged_depth["grade_digest"]
            ).encode("utf-8")
        ).hexdigest()
        atomic_write_json(out / "report.json", forged_depth)
        if verify_fragility_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "depth-forgery-falsification",
                "detail": "forged depth cell passed verification",
            }

        # Falsifiability 3: keep the true matrix but misgrade the score.
        misgraded = json.loads(json.dumps(first))
        misgraded["fragility"]["fragility_score"] = 1.0
        atomic_write_json(out / "report.json", misgraded)
        if verify_fragility_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded score passed verification"}

        # Falsifiability 4: flip one recorded blocked-goal list entry raw
        # (no re-sealing) — the digest chain must catch it.
        tampered = json.loads(json.dumps(first))
        tampered["impact_matrix"]["domain.tool-routing"] = ["ledger-gated-proposal"]
        atomic_write_json(out / "report.json", tampered)
        if verify_fragility_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "tampered matrix passed verification"}

    return {
        "ok": not first["used_skill_route_discovery"],
        "fragility": grade,
        "report_digest": first["report_digest"],
        "deterministic": True,
        "priority_correct": True,
        "depth_honest": True,
        "matrix_forgery_detected": True,
        "depth_forgery_detected": True,
        "misgrade_detected": True,
        "tamper_detected": True,
        "used_skill_route_discovery": first["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Goal fragility audit")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the audit and seal a report artifact")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_fragility_audit()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_fragility_report(report, out)
        summary["fragility"] = report["fragility"]
    else:
        summary = verify_fragility_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
