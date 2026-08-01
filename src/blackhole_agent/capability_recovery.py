"""Capability recovery loop: goal-directed repair closes the application plane.

The application plane plans goals over the *live proved* ledger: a capability
whose proof stamp is red is excluded, and a goal that needs it is honestly
unplannable. The repair plane can diagnose and heal one red capability. This
module closes those two into one loop:

1. **detect** — plan every application goal; the goals with no plan name the
   unproved capabilities that block them;
2. **repair** — bounded deterministic repair (``repair_capability``: diagnose,
   regenerate stale proof interpreter, re-prove the dependency chain) of every
   blocked capability, on a scratch ledger clone unless ``persist`` is given;
3. **re-plan** — rebuild the registry from the post-repair ledger, re-plan,
   execute, and grade outcomes against the frozen oracles;
4. **honesty** — a capability that repairs green must unblock its goals; a
   capability that is unrepairable must leave its goals unsolved and its
   stamp red. Correlated breaks (several red capabilities at once) are
   repaired one bounded attempt each; a red root dependency with a healthy
   proof command heals transitively through a repaired member's
   dependency-chain re-proof, and the post-loop stamps of every broken
   capability are recorded as falsifiable evidence. Fake healing is a
   verification failure, not a result.

The report is digest-sealed under ``artifacts/capability-recovery/``.
Verification is pure: it recomputes the grade from recorded task and repair
outcomes, re-checks the digest chain, re-checks every solved plan against the
live ledger, and enforces recovery consistency — a goal recorded as unsolved
must be backed by an ``unrepairable`` verdict, and a goal recorded as solved
may only use capabilities that are green in the live ledger and whose
recorded repairs healed.

Synthetic breaks run on deep-copied scratch ledgers; the live ledger is only
mutated when ``persist=True`` is requested explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from blackhole_agent.durable_state import durable_read_path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_application import (
    APPLICATION_STEPS,
    APPLICATION_TASKS,
    _capability_proved,
    build_application_registry,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    CapabilityLedger,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.capability_repair import (
    FAILING_PROOF,
    _clone_ledger,
    _replace_capability_fields,
    _swap_proof_interpreter,
    repair_capability,
)

SCHEMA_VERSION = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = "artifacts/capability-recovery"
LATEST_POINTER = REPO_ROOT / DEFAULT_ARTIFACT_DIR / "latest-recovery.json"

BOGUS_INTERPRETER = str(REPO_ROOT / ".blackhole-recovery-nonexistent" / "Scripts" / "python.exe")

# Synthetic break modes applied to a scratch ledger clone.
BREAK_STALE_INTERPRETER = "stale_interpreter"
BREAK_FAILING_PROOF = "failing_proof"
BREAK_STALE_STAMP = "stale_stamp"


def apply_synthetic_break(
    ledger: CapabilityLedger, capability_id: str, mode: str
) -> CapabilityLedger:
    """Break one capability's proof stamp on a scratch ledger clone."""

    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        raise KeyError(capability_id)
    if mode == BREAK_STALE_INTERPRETER:
        return _replace_capability_fields(
            ledger,
            capability_id,
            proof_command=_swap_proof_interpreter(capability.proof_command, BOGUS_INTERPRETER),
            last_proof_exit_code=1,
            last_proved_at="",
        )
    if mode == BREAK_FAILING_PROOF:
        return _replace_capability_fields(
            ledger,
            capability_id,
            proof_command=FAILING_PROOF,
            last_proof_exit_code=1,
            last_proved_at="",
        )
    if mode == BREAK_STALE_STAMP:
        # The proof command is healthy; only the recorded stamp is falsified
        # red. A re-proof of the dependency chain heals this transitively.
        return _replace_capability_fields(
            ledger,
            capability_id,
            last_proof_exit_code=1,
            last_proved_at="",
        )
    raise ValueError(f"unknown break mode: {mode}")


def _repair_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    """Stable fields of one repair verdict (durations/replay text excluded)."""

    return {
        "capability_id": report.get("capability_id"),
        "verdict": report.get("verdict"),
        "repair_actions": list(report.get("repair_actions") or []),
        "honest": bool(report.get("honest")),
        "last_proof_exit_code": report.get("last_proof_exit_code"),
    }


def run_recovery_loop(
    *,
    breaks: Mapping[str, str] | None = None,
    persist: bool = False,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
) -> dict[str, Any]:
    """Detect blocked goals, repair what blocks them, re-plan, grade.

    ``breaks`` maps capability ids to synthetic break modes; when given, the
    whole loop runs on a scratch clone and the live ledger is never touched
    unless ``persist=True``.
    """

    path = default_ledger_path(REPO_ROOT)
    live = load_ledger(path)
    requested = dict(breaks or {})
    ledger = _clone_ledger(live) if requested else live
    applied_breaks: list[dict[str, Any]] = []
    for capability_id, mode in sorted(requested.items()):
        ledger = apply_synthetic_break(ledger, capability_id, mode)
        applied_breaks.append({"capability_id": capability_id, "mode": mode})

    # Phase 1: detect — which goals have no plan over the current stamps?
    registry = build_application_registry(ledger)
    initial_plans = {
        task.id: plan_application_task(task, registry) for task in APPLICATION_TASKS
    }
    blocked_capabilities = sorted(
        capability_id
        for capability_id in APPLICATION_STEPS
        if not _capability_proved(ledger, capability_id)
    )

    # Phase 2: repair — bounded, one attempt per blocked capability, widest
    # blast radius first: the failure that blocks the most goals is healed
    # before failures that block fewer. Blast radii come from the *healthy*
    # surface structure (the live ledger), not the broken clone — a red
    # capability is absent from its own impact matrix.
    from blackhole_agent.capability_fragility import blast_radius_map

    blast = blast_radius_map(live)
    blocked_capabilities.sort(key=lambda cid: (-blast.get(cid, 0), cid))
    repairs: list[dict[str, Any]] = []
    for capability_id in blocked_capabilities:
        ledger, report = repair_capability(
            ledger,
            capability_id,
            cwd=REPO_ROOT,
            command_runner=command_runner,
            timeout=timeout,
        )
        projection = _repair_projection(report)
        projection["blast_radius"] = blast.get(capability_id, 0)
        repairs.append(projection)
    if persist and not requested and repairs:
        save_ledger(path, ledger)

    # Phase 3: re-plan, execute, grade against the frozen oracles.
    registry = build_application_registry(ledger)
    task_records: list[dict[str, Any]] = []
    for task in APPLICATION_TASKS:
        started = time.perf_counter()
        result = run_application_task(task, registry)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        plan = result["plan"] or []
        task_records.append(
            {
                "id": task.id,
                "initially_unplannable": initial_plans[task.id] is None,
                "ok": result["ok"],
                "plan": result["plan"],
                "plan_sound": bool(plan)
                and all(_capability_proved(ledger, capability_id) for capability_id in plan),
                "outcome": result["outcome"],
                "error": result["error"],
                "duration_ms": duration_ms,
            }
        )

    # Post-loop stamps of every broken capability, including non-surface
    # dependencies that were never repaired directly — this is where
    # transitive dependency healing becomes falsifiable evidence.
    break_stamps_after = {
        capability_id: ledger.capabilities[capability_id].last_proof_exit_code
        for capability_id in sorted(requested)
    }

    grade = compute_recovery_grade(task_records, repairs)
    breaks_digest = _digest({"breaks": applied_breaks, "stamps_after": break_stamps_after})
    repairs_digest = _digest(repairs)
    tasks_digest = _digest(
        [
            {
                "id": record["id"],
                "initially_unplannable": record["initially_unplannable"],
                "ok": record["ok"],
                "plan": record["plan"],
                "outcome": record["outcome"],
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(grade)
    report_digest = hashlib.sha256(
        f"recovery:{breaks_digest}:{repairs_digest}:{tasks_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_recovery_loop",
        "run_at": utc_now_iso(),
        "applied_breaks": applied_breaks,
        "break_stamps_after": break_stamps_after,
        "blocked_capabilities": blocked_capabilities,
        "repairs": repairs,
        "task_records": task_records,
        "recovery": grade,
        "breaks_digest": breaks_digest,
        "repairs_digest": repairs_digest,
        "tasks_digest": tasks_digest,
        "grade_digest": grade_digest,
        "report_digest": report_digest,
        "ok": (
            grade["task_pass_count"] == grade["task_count"]
            and grade["unsolved_count"] == 0
            and all(record["plan_sound"] for record in task_records)
            and all(repair["honest"] for repair in repairs)
        ),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def compute_recovery_grade(
    task_records: Sequence[Mapping[str, Any]],
    repairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pure recovery derivation from recorded task and repair outcomes.

    A goal is **recovered** when it had no plan before the loop and matches
    its oracle after it. A goal is an **honest unsolved** when it had no plan,
    still fails, and some recorded repair verdict is ``unrepairable`` — the
    loop said it could not heal and the outcome agrees. This function is the
    single grading rule: a report whose recorded grade disagrees with its
    recorded outcomes is misgraded and fails verification.
    """

    unrepairable_seen = any(repair.get("verdict") == "unrepairable" for repair in repairs)
    recovered: list[str] = []
    honest_unsolved: list[str] = []
    for record in task_records:
        if not record.get("initially_unplannable"):
            continue
        if record.get("ok"):
            recovered.append(str(record.get("id")))
        elif unrepairable_seen:
            honest_unsolved.append(str(record.get("id")))
    return {
        "task_pass_count": sum(1 for record in task_records if record.get("ok")),
        "task_count": len(task_records),
        "unsolved_count": sum(1 for record in task_records if not record.get("ok")),
        "repair_count": len(repairs),
        "repaired_count": sum(1 for repair in repairs if repair.get("verdict") == "repaired"),
        "unrepairable_count": sum(1 for repair in repairs if repair.get("verdict") == "unrepairable"),
        "recovered": recovered,
        "honest_unsolved": honest_unsolved,
    }


def check_recovery_consistency(
    task_records: Sequence[Mapping[str, Any]],
    repairs: Sequence[Mapping[str, Any]],
    ledger: CapabilityLedger,
    *,
    break_stamps_after: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    """Cross-checks that make fake healing a verification failure.

    - every solved goal's plan uses only capabilities green in the live
      ledger, and any recorded repair of a plan member healed;
    - every unsolved initially-blocked goal is backed by an ``unrepairable``
      verdict (the loop failed honestly, not silently);
    - every repair stamped honest kept its stamp consistent with its verdict;
    - when post-loop break stamps are recorded, each verdict must match the
      stamp it produced: ``repaired`` leaves a green stamp, ``unrepairable``
      leaves a red one — a forged verdict contradicts its own stamp.
    """

    repair_verdicts = {str(repair.get("capability_id")): str(repair.get("verdict")) for repair in repairs}
    solved_plans_sound = True
    for record in task_records:
        if not record.get("ok"):
            continue
        for capability_id in record.get("plan") or []:
            if not _capability_proved(ledger, capability_id):
                solved_plans_sound = False
            verdict = repair_verdicts.get(capability_id)
            if verdict is not None and verdict not in {"repaired", "healthy"}:
                solved_plans_sound = False
    unsolved_backed = True
    unrepairable_seen = any(repair.get("verdict") == "unrepairable" for repair in repairs)
    for record in task_records:
        if record.get("initially_unplannable") and not record.get("ok") and not unrepairable_seen:
            unsolved_backed = False
    repairs_honest = all(bool(repair.get("honest")) for repair in repairs)
    checks = {
        "solved_plans_sound": solved_plans_sound,
        "unsolved_backed_by_unrepairable": unsolved_backed,
        "repairs_honest": repairs_honest,
    }
    if break_stamps_after is not None:
        stamps_match_verdicts = True
        for repair in repairs:
            capability_id = str(repair.get("capability_id"))
            if capability_id not in break_stamps_after:
                continue
            stamp = break_stamps_after[capability_id]
            verdict = str(repair.get("verdict"))
            if verdict == "repaired" and stamp != 0:
                stamps_match_verdicts = False
            if verdict == "unrepairable" and stamp == 0:
                stamps_match_verdicts = False
        checks["stamps_match_verdicts"] = stamps_match_verdicts
    return checks


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def write_recovery_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Seal the recovery report artifact and refresh the latest pointer."""

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
        "recovered": (report.get("recovery") or {}).get("recovered"),
    }


def verify_recovery_report(report_dir: Path) -> dict[str, Any]:
    """Recompute every digest, re-grade, and enforce recovery consistency.

    Verification never re-executes a repair or a pipeline. A report whose
    task outcomes were flipped, whose grade was miscomputed, whose repair
    verdicts were forged to fake a healing, or whose solved plans name a
    capability not green in the live ledger fails verification.
    """

    report_path = report_dir / "report.json"
    if not durable_read_path(report_path).exists():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(durable_read_path(report_path).read_text(encoding="utf-8"))
    task_records = report.get("task_records") or []
    repairs = report.get("repairs") or []

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    regraded = compute_recovery_grade(task_records, repairs)
    breaks_digest = _digest(
        {
            "breaks": report.get("applied_breaks") or [],
            "stamps_after": report.get("break_stamps_after") or {},
        }
    )
    repairs_digest = _digest(repairs)
    tasks_digest = _digest(
        [
            {
                "id": record.get("id"),
                "initially_unplannable": record.get("initially_unplannable"),
                "ok": record.get("ok"),
                "plan": record.get("plan"),
                "outcome": record.get("outcome"),
            }
            for record in task_records
        ]
    )
    grade_digest = _digest(regraded)
    report_digest = hashlib.sha256(
        f"recovery:{breaks_digest}:{repairs_digest}:{tasks_digest}:{grade_digest}".encode("utf-8")
    ).hexdigest()

    consistency = check_recovery_consistency(
        task_records,
        repairs,
        ledger,
        break_stamps_after=report.get("break_stamps_after") or {},
    )
    checks = {
        "breaks_digest": breaks_digest == report.get("breaks_digest"),
        "repairs_digest": repairs_digest == report.get("repairs_digest"),
        "tasks_digest": tasks_digest == report.get("tasks_digest"),
        "grade_recomputed_matches": regraded == report.get("recovery"),
        "grade_digest": grade_digest == report.get("grade_digest"),
        "report_digest": report_digest == report.get("report_digest"),
        **consistency,
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report_digest}


def builtin_recovery_loop() -> dict[str, Any]:
    """Registered proof for ``capability.recovery-loop``.

    Proves the loop end to end: a baseline run over the healthy live ledger
    solves every goal with zero repairs; a correlated stale-interpreter break
    of two capabilities (``domain.tool-routing`` + ``domain.issue-triage``)
    is detected, both are repaired, and the blocked goal is recovered with an
    oracle-matching outcome — deterministically across two runs; a transitive
    break (red stamp on the root dependency ``repo.import-health`` plus a
    stale interpreter on ``domain.tool-routing``) heals the root through the
    repaired member's dependency-chain re-proof without any direct repair of
    the root; a mixed break (one healable, one unrepairable) recovers the
    healable goal and honestly leaves the unrepairable goals unsolved with
    the stamps red; and an unrepairable break of
    ``capability.ledger-inventory`` is absorbed by redundancy — the
    alternative readiness provider carries every goal, so a formerly fatal
    break becomes a recorded non-event. Then report sealing plus three
    falsifications: a flipped task outcome, a forged repair verdict (fake
    healing), and a misgraded recovery score must all fail verification.
    """

    import os
    import tempfile

    baseline = run_recovery_loop()
    if not baseline["ok"] or baseline["recovery"]["repair_count"] != 0:
        return {"ok": False, "stage": "baseline", "recovery": baseline["recovery"]}

    # Correlated break: two surface capabilities red at once.
    correlated_breaks = {
        "domain.issue-triage": BREAK_STALE_INTERPRETER,
        "domain.tool-routing": BREAK_STALE_INTERPRETER,
    }
    correlated_first = run_recovery_loop(breaks=correlated_breaks)
    correlated_second = run_recovery_loop(breaks=correlated_breaks)
    healed = (
        correlated_first["ok"]
        and correlated_first["recovery"]["recovered"] == ["routed-triage-record"]
        and correlated_first["recovery"]["repaired_count"] == 2
        and all(
            any(
                repair["capability_id"] == capability_id
                and repair["verdict"] == "repaired"
                and "regenerate_proof_command" in repair["repair_actions"]
                for repair in correlated_first["repairs"]
            )
            for capability_id in correlated_breaks
        )
        and correlated_first["break_stamps_after"] == {capability_id: 0 for capability_id in correlated_breaks}
    )
    if not healed:
        return {"ok": False, "stage": "correlated-heal", "recovery": correlated_first["recovery"]}
    determinism = (
        correlated_first["repairs_digest"] == correlated_second["repairs_digest"]
        and correlated_first["tasks_digest"] == correlated_second["tasks_digest"]
        and correlated_first["breaks_digest"] == correlated_second["breaks_digest"]
    )
    if not determinism:
        return {"ok": False, "stage": "determinism"}

    # Transitive break: the root dependency's stamp is falsified red and a
    # surface member's interpreter is stale. Repairing the member re-proves
    # its dependency chain, healing the root without a direct repair entry.
    transitive = run_recovery_loop(
        breaks={
            "repo.import-health": BREAK_STALE_STAMP,
            "domain.tool-routing": BREAK_STALE_INTERPRETER,
        }
    )
    transitive_healed = (
        transitive["ok"]
        and transitive["recovery"]["recovered"] == ["routed-triage-record"]
        and transitive["recovery"]["repaired_count"] == 1
        and transitive["break_stamps_after"].get("repo.import-health") == 0
        and transitive["break_stamps_after"].get("domain.tool-routing") == 0
        and not any(repair["capability_id"] == "repo.import-health" for repair in transitive["repairs"])
    )
    if not transitive_healed:
        return {"ok": False, "stage": "transitive-heal", "recovery": transitive["recovery"]}

    # Mixed break: one healable, one unrepairable — partial honest recovery.
    # The unrepairable capability (domain.ci-security, blast radius 2) is
    # repaired before the one-goal failure, and both of its goals stay
    # honestly unsolved while the healable goal recovers.
    mixed = run_recovery_loop(
        breaks={
            "domain.tool-routing": BREAK_STALE_INTERPRETER,
            "domain.ci-security": BREAK_FAILING_PROOF,
        }
    )
    honest_failure = (
        not mixed["ok"]
        and mixed["recovery"]["recovered"] == ["routed-triage-record"]
        and mixed["recovery"]["honest_unsolved"] == ["scan-gated-activation", "blocked-scan-honesty"]
        and mixed["recovery"]["unrepairable_count"] == 1
        and mixed["recovery"]["repaired_count"] == 1
        and mixed["break_stamps_after"].get("domain.ci-security") != 0
        and mixed["break_stamps_after"].get("domain.tool-routing") == 0
        and mixed["recovery"]["task_pass_count"] == mixed["recovery"]["task_count"] - 2
        # Blast-radius priority: the two-goal failure is repaired before the
        # one-goal failure, and the order is digest-covered evidence.
        and [repair["capability_id"] for repair in mixed["repairs"]]
        == ["domain.ci-security", "domain.tool-routing"]
        and mixed["repairs"][0]["blast_radius"] == 2
        and mixed["repairs"][1]["blast_radius"] == 1
    )
    if not honest_failure:
        return {"ok": False, "stage": "honest-failure", "recovery": mixed["recovery"]}

    # Redundancy absorption: capability.ledger-inventory is unrepairable, yet
    # every goal still solves — the redundant readiness provider
    # (capability.ledger-attestation) carries both readiness-gated goals.
    # What was a fatal break before redundancy engineering is now a
    # non-event, recorded honestly (unrepairable, stamp left red).
    absorbed = run_recovery_loop(breaks={"capability.ledger-inventory": BREAK_FAILING_PROOF})
    redundancy_absorbed = (
        absorbed["ok"]
        and absorbed["recovery"]["unsolved_count"] == 0
        and absorbed["recovery"]["task_pass_count"] == absorbed["recovery"]["task_count"]
        and absorbed["recovery"]["unrepairable_count"] == 1
        and absorbed["recovery"]["honest_unsolved"] == []
        and absorbed["break_stamps_after"].get("capability.ledger-inventory") != 0
        and all(record["plan"] for record in absorbed["task_records"])
    )
    if not redundancy_absorbed:
        return {"ok": False, "stage": "redundancy-absorption", "recovery": absorbed["recovery"]}

    report_dir_raw = (os.environ.get("BLACKHOLE_RECOVERY_REPORT_DIR") or "").strip()
    if report_dir_raw:
        out = Path(report_dir_raw)
        out.mkdir(parents=True, exist_ok=True)
        write_recovery_report(correlated_first, out)
        verified = verify_recovery_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}
        return {
            "ok": True,
            "recovery": correlated_first["recovery"],
            "honest_failure": mixed["recovery"],
            "report_digest": correlated_first["report_digest"],
            "report_dir": str(out),
            "deterministic": True,
            "used_skill_route_discovery": correlated_first["used_skill_route_discovery"],
        }

    with tempfile.TemporaryDirectory(prefix="capability-recovery-proof-") as tmp:
        out = Path(tmp) / "report"
        write_recovery_report(correlated_first, out)
        verified = verify_recovery_report(out)
        if not verified["ok"]:
            return {"ok": False, "stage": "verify", "checks": verified.get("checks")}

        # Falsifiability 1: flip one recorded task outcome; verification must fail.
        tampered = json.loads(durable_read_path(out / "report.json").read_text(encoding="utf-8"))
        tampered["task_records"][0]["ok"] = not tampered["task_records"][0]["ok"]
        atomic_write_json(out / "report.json", tampered)
        if verify_recovery_report(out)["ok"]:
            return {"ok": False, "stage": "tamper-falsification", "detail": "flipped outcome passed verification"}

        # Falsifiability 2: fake a healing — forge the mixed scenario's
        # unrepairable verdict to "repaired" and re-seal every digest. The
        # consistency cross-checks must catch it twice over: the goal stayed
        # unsolved with no unrepairable verdict backing it, and the forged
        # verdict contradicts the recorded red stamp.
        forged = json.loads(json.dumps(mixed))
        for repair in forged["repairs"]:
            if repair["capability_id"] == "domain.ci-security":
                repair["verdict"] = "repaired"
        forged["repairs_digest"] = _digest(forged["repairs"])
        forged["recovery"] = compute_recovery_grade(forged["task_records"], forged["repairs"])
        forged["grade_digest"] = _digest(forged["recovery"])
        forged["report_digest"] = hashlib.sha256(
            "recovery:{}:{}:{}:{}".format(
                forged["breaks_digest"], forged["repairs_digest"], forged["tasks_digest"], forged["grade_digest"]
            ).encode("utf-8")
        ).hexdigest()
        atomic_write_json(out / "report.json", forged)
        if verify_recovery_report(out)["ok"]:
            return {
                "ok": False,
                "stage": "fake-healing-falsification",
                "detail": "forged repair verdict passed verification",
            }

        # Falsifiability 3: restore the healing report but misgrade the score.
        misgraded = json.loads(json.dumps(correlated_first))
        misgraded["recovery"]["task_pass_count"] = 0
        atomic_write_json(out / "report.json", misgraded)
        if verify_recovery_report(out)["ok"]:
            return {"ok": False, "stage": "misgrade-falsification", "detail": "misgraded recovery passed verification"}

    return {
        "ok": not correlated_first["used_skill_route_discovery"],
        "recovery": correlated_first["recovery"],
        "honest_failure": mixed["recovery"],
        "absorbed": absorbed["recovery"],
        "report_digest": correlated_first["report_digest"],
        "deterministic": True,
        "healed": True,
        "transitive_healed": True,
        "honest_unsolved": True,
        "redundancy_absorbed": True,
        "tamper_detected": True,
        "fake_healing_detected": True,
        "misgrade_detected": True,
        "used_skill_route_discovery": correlated_first["used_skill_route_discovery"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability recovery loop")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run the loop over the live ledger and seal a report")
    mode.add_argument("--verify", type=Path, help="verify a sealed report directory")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.run:
        report = run_recovery_loop()
        stamp = report["run_at"].replace(":", "").replace("-", "")
        out = args.output_dir or (REPO_ROOT / DEFAULT_ARTIFACT_DIR / stamp)
        summary = write_recovery_report(report, out)
        summary["recovery"] = report["recovery"]
    else:
        summary = verify_recovery_report(args.verify)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
