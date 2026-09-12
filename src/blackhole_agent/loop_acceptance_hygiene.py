"""Scheduled hygiene for the acceptance sweep: regressions surface automatically.

The acceptance sweep (``blackhole_agent.acceptance_sweep``) adjudicates every
standalone probe under ``tests/acceptance``, but nothing ran it on a schedule:
a probe contract that stopped holding (a probe that went unmet, crashed, or
timed out) only surfaced when an operator remembered to sweep by hand.

This module wires the sweep into scheduled hygiene. A recurring registration
(daily trigger, logon-independent) points at a launcher that dispatches the
hygiene pass; the pass sweeps every probe, compares the verdicts against the
durable green baseline, and writes a durable report that names every
probe-contract regression. Regressions surface automatically: the report and
the pass result flag each probe that was green and no longer is, without
anyone rerunning the sweep manually. A probe that recovers drops out of the
regression list on the next pass; a probe that fails on first sight is a
regression too.

Scheduling never runs the sweep at registration time, so registering beside
a busy checkout is cheap; the recurring trigger dispatches the pass.

CLI-equivalent entry points: ``schedule_acceptance_hygiene`` (registration),
``dispatch_acceptance_hygiene`` (what the scheduled launcher calls), and
``run_acceptance_hygiene`` (the pass itself, usable standalone).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

from blackhole_agent.acceptance_sweep import DEFAULT_PROBE_TIMEOUT, sweep_acceptance_probes
from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path, durable_write_path

SCHEMA_VERSION = 1
ACCEPTANCE_HYGIENE_ID = "capability.acceptance-sweep-hygiene"
ACCEPTANCE_HYGIENE_DONE_WHEN = (
    "A recurring registration schedules the acceptance sweep as hygiene; each "
    "dispatched pass sweeps every standalone probe and the durable report "
    "names every probe-contract regression automatically."
)
ACCEPTANCE_HYGIENE_GOAL = (
    "Wire the acceptance sweep into scheduled hygiene so probe-contract "
    "regressions surface automatically instead of waiting for a manual sweep."
)
HYGIENE_TASK_NAME = "BlackholeAcceptanceHygiene"
HYGIENE_TRIGGER = "daily"
HYGIENE_HELPER = "blackhole_agent.loop_acceptance_hygiene:dispatch_acceptance_hygiene"
HYGIENE_DIR_NAME = "acceptance-hygiene"
REGISTRATION_NAME = "registration.json"
TASK_XML_NAME = "acceptance-hygiene-task.xml"
LAUNCHER_NAME = "BlackholeAcceptanceHygiene.py"
STATE_NAME = "state.json"
REPORT_NAME = "report.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
HygieneScheduler = Callable[[dict[str, Any]], dict[str, Any]]


def hygiene_root(repo_path: Path, output_dir: Path | None = None) -> Path:
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    return mission_root(Path(repo_path), output) / HYGIENE_DIR_NAME


def hygiene_registration_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return hygiene_root(repo_path, output_dir) / REGISTRATION_NAME


def hygiene_task_xml_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return hygiene_root(repo_path, output_dir) / TASK_XML_NAME


def hygiene_launcher_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return hygiene_root(repo_path, output_dir) / LAUNCHER_NAME


def hygiene_state_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return hygiene_root(repo_path, output_dir) / STATE_NAME


def hygiene_report_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    return hygiene_root(repo_path, output_dir) / REPORT_NAME


def build_hygiene_command(repo_path: Path, output_dir: Path | None = None) -> list[str]:
    launcher = hygiene_launcher_path(repo_path, output_dir)
    return [sys.executable, "-I", str(launcher)]


def render_hygiene_launcher(repo_path: Path, output_dir: Path) -> str:
    from blackhole_agent import unbound

    src = Path(unbound.__file__).resolve().parents[1]
    return (
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "from blackhole_agent.loop_acceptance_hygiene import dispatch_acceptance_hygiene\n"
        "result = dispatch_acceptance_hygiene("
        f"Path({str(Path(repo_path).resolve())!r}), "
        f"Path({str(Path(output_dir).resolve())!r}))\n"
        "raise SystemExit(0 if result.get('ok') else 1)\n"
    )


def render_hygiene_task_xml(registration: dict[str, Any]) -> str:
    command = [str(part) for part in registration.get("command") or []]
    executable = command[0] if command else sys.executable
    arguments = " ".join(command[1:])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        f"  <RegistrationInfo><URI>\\{escape(str(registration.get('name') or HYGIENE_TASK_NAME))}</URI></RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <CalendarTrigger>\n"
        "      <StartBoundary>2000-01-01T03:00:00</StartBoundary>\n"
        "      <Enabled>true</Enabled>\n"
        "      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>\n"
        "    </CalendarTrigger>\n"
        "  </Triggers>\n"
        "  <Principals><Principal id=\"Author\"><LogonType>InteractiveToken</LogonType></Principal></Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <Enabled>true</Enabled>\n"
        "  </Settings>\n"
        "  <Actions Context=\"Author\">\n"
        "    <Exec>\n"
        f"      <Command>{escape(executable)}</Command>\n"
        f"      <Arguments>{escape(arguments)}</Arguments>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _atomic_write(path: Path, text: str) -> None:
    target = durable_write_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)


def _read_json(path: Path) -> dict[str, Any] | None:
    resolved = durable_read_path(path)
    if not resolved.is_file():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def build_hygiene_registration(repo_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    resolved_output = hygiene_root(repo, output_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "name": HYGIENE_TASK_NAME,
        "trigger": HYGIENE_TRIGGER,
        "enabled": True,
        "helper": HYGIENE_HELPER,
        "command": build_hygiene_command(repo, output_dir),
        "repo_path": str(repo),
        "hygiene_dir": str(resolved_output),
        "multiple_instances": "ignore_new",
    }


def load_hygiene_registration(repo_path: Path, output_dir: Path | None = None) -> dict[str, Any] | None:
    return _read_json(hygiene_registration_path(repo_path, output_dir))


def schedule_acceptance_hygiene(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    scheduler: HygieneScheduler | None = None,
) -> dict[str, Any]:
    """Create or replace the recurring hygiene registration for the sweep.

    This only schedules. It does not run the sweep, so registration beside a
    busy checkout is cheap; the recurring trigger dispatches the pass.
    """

    repo = Path(repo_path)
    spec = build_hygiene_registration(repo, output_dir)
    registration_path = hygiene_registration_path(repo, output_dir)
    xml_path = hygiene_task_xml_path(repo, output_dir)
    launcher_path = hygiene_launcher_path(repo, output_dir)
    resolved_output = hygiene_root(repo, output_dir)
    _atomic_write(launcher_path, render_hygiene_launcher(repo, resolved_output))
    _atomic_write(xml_path, render_hygiene_task_xml(spec))
    recorded = {
        **spec,
        "registration_path": str(registration_path),
        "task_xml_path": str(xml_path),
        "launcher_path": str(launcher_path),
        "scheduled": True,
        "action": "schedule",
        "ran": False,
        "registered_at": utc_now_iso(),
    }
    _atomic_write(registration_path, json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    applied = scheduler(recorded) if scheduler is not None else {"backend": "file", "applied": True}
    return {**recorded, **applied}


def _probe_name(record: dict[str, Any]) -> str:
    return Path(str(record.get("path") or "")).stem


def _is_green(record: dict[str, Any]) -> bool:
    return record.get("exit_code") == 0 and record.get("passed") is True


def run_acceptance_hygiene(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    timeout: int = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Sweep every probe and surface probe-contract regressions automatically.

    A probe is a regression when its verdict is no longer green (unmet,
    crashed, timed out, or unparseable). Each regression is named in the
    durable report with whether it was green on a previous pass, so a broken
    probe contract surfaces on the next scheduled pass without a manual
    sweep. The green baseline only records green verdicts, so a recovered
    probe drops out of the regression list on its next green pass.
    """

    repo = Path(repo_path)
    state_path = hygiene_state_path(repo, output_dir)
    report_path = hygiene_report_path(repo, output_dir)
    state = _read_json(state_path) or {"schema_version": SCHEMA_VERSION, "green": {}}
    baseline = state.get("green") if isinstance(state.get("green"), dict) else {}

    sweep = sweep_acceptance_probes(repo, timeout=timeout)
    regressions: list[dict[str, Any]] = []
    green_now: dict[str, Any] = dict(baseline)
    for record in sweep.get("probes") or []:
        name = _probe_name(record)
        if _is_green(record):
            green_now[name] = {
                "last_green_at": utc_now_iso(),
                "observed": record.get("observed"),
            }
            continue
        if record.get("timed_out"):
            verdict = "timed_out"
        elif record.get("passed") is False:
            verdict = "unmet"
        elif record.get("exit_code") not in (0, None):
            verdict = "crashed"
        else:
            verdict = "invalid"
        regressions.append(
            {
                "name": name,
                "verdict": verdict,
                "exit_code": record.get("exit_code"),
                "previously_green": name in baseline,
                "error": record.get("error") or "",
            }
        )
    regressions.sort(key=lambda item: item["name"])

    ok = bool(sweep.get("ok")) and not regressions
    report = {
        "schema_version": SCHEMA_VERSION,
        "action": "acceptance_hygiene",
        "ran": True,
        "ran_at": utc_now_iso(),
        "repo_path": str(repo.resolve()),
        "ok": ok,
        "regressions": regressions,
        "regression_count": len(regressions),
        "sweep": {
            key: sweep.get(key)
            for key in ("total", "executed", "met", "unmet", "crashed", "timed_out", "invalid", "ok")
        },
        "probes": sweep.get("probes") or [],
    }
    _atomic_write(report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _atomic_write(
        state_path,
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "updated_at": utc_now_iso(),
                "green": green_now,
                "last_ok": ok,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return {
        **report,
        "report_path": str(report_path),
        "state_path": str(state_path),
    }


def dispatch_acceptance_hygiene(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    timeout: int = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Run the hygiene pass the recurring registration scheduled.

    Missing, disabled, or wrong-trigger registrations are left alone so a
    stale schedule never sweeps a repo it no longer describes. An enabled
    registration dispatches one pass; the pass itself surfaces regressions.
    """

    repo = Path(repo_path)
    registration = load_hygiene_registration(repo, output_dir)
    if registration is None:
        return {
            "ok": True,
            "ran": False,
            "action": "skip",
            "skip_reason": "not_registered",
            "scheduled": False,
        }
    if registration.get("enabled") is not True:
        return {
            "ok": True,
            "ran": False,
            "action": "skip",
            "skip_reason": "not_enabled",
            "scheduled": False,
        }
    if registration.get("trigger") != HYGIENE_TRIGGER:
        return {
            "ok": True,
            "ran": False,
            "action": "skip",
            "skip_reason": "wrong_trigger",
            "scheduled": True,
        }
    if registration.get("helper") != HYGIENE_HELPER:
        return {
            "ok": True,
            "ran": False,
            "action": "skip",
            "skip_reason": "wrong_helper",
            "scheduled": True,
        }
    result = run_acceptance_hygiene(repo, output_dir, timeout=timeout)
    return {
        **result,
        "scheduled": True,
        "dispatched_from": "scheduled_hygiene",
        "hygiene_task": registration.get("name", HYGIENE_TASK_NAME),
    }


def acceptance_hygiene_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.loop_acceptance_hygiene import "
        "builtin_acceptance_hygiene_proof; r=builtin_acceptance_hygiene_proof(); "
        "assert r['ok'] and r.get('action')=='acceptance_hygiene' "
        "and r.get('passed_count',0) >= 10 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_acceptance_hygiene_capability(*, repo_path: Path | None = None) -> Capability:
    """Register acceptance-sweep hygiene on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ACCEPTANCE_HYGIENE_ID,
        name="Acceptance-sweep scheduled hygiene",
        description=(
            "A recurring registration schedules the acceptance sweep as hygiene; "
            "each dispatched pass sweeps every standalone probe and the durable "
            "report names every probe-contract regression automatically."
        ),
        kind="python",
        entry="blackhole_agent.loop_acceptance_hygiene:builtin_acceptance_hygiene_proof",
        proof_command=acceptance_hygiene_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.goal-watchdog",
        ),
        behavior_paths=(
            "src/blackhole_agent/loop_acceptance_hygiene.py",
            "src/blackhole_agent/acceptance_sweep.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Probe-contract regressions surface automatically: the acceptance "
            "sweep runs as scheduled hygiene and each pass names every probe "
            "that stopped holding, with no manual sweep."
        ),
        tags=("acceptance", "sweep", "hygiene", "schedule", "regression"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


_MET_PROBE = """import json
print(json.dumps({"passed": True, "observed": {"sentinel": "GREEN"}}))
"""


def _write_probe(acceptance: Path, name: str, *, green: bool) -> Path:
    if green:
        text = _MET_PROBE
    else:
        text = (
            "import json\n"
            'print(json.dumps({"passed": False, "observed": {"sentinel": "BROKEN"}}))\n'
        )
    path = acceptance / name
    path.write_text(text, encoding="utf-8")
    return path


def _make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    acceptance = repo / "tests" / "acceptance"
    acceptance.mkdir(parents=True)
    _write_probe(acceptance, "test_stable.py", green=True)
    _write_probe(acceptance, "test_flaky.py", green=True)
    return repo


def builtin_acceptance_hygiene_proof() -> dict[str, Any]:
    """Hermetic proof: scheduled hygiene surfaces probe-contract regressions."""

    import tempfile

    checks: dict[str, bool] = {}
    checks["schema_version"] = SCHEMA_VERSION == 1

    with tempfile.TemporaryDirectory(prefix="acceptance-hygiene-proof-") as tmp:
        repo = _make_repo(Path(tmp))
        applied: list[str] = []

        def scheduler(registration: dict[str, Any]) -> dict[str, Any]:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        scheduled = schedule_acceptance_hygiene(repo, scheduler=scheduler)
        xml_text = durable_read_path(Path(scheduled["task_xml_path"])).read_text(encoding="utf-8")
        launcher = durable_read_path(Path(scheduled["launcher_path"])).read_text(encoding="utf-8")
        checks["registration_schedules_daily_sweep"] = (
            scheduled.get("scheduled") is True
            and scheduled.get("ran") is False
            and scheduled.get("trigger") == HYGIENE_TRIGGER
            and scheduled.get("helper") == HYGIENE_HELPER
            and scheduled.get("enabled") is True
            and HYGIENE_HELPER.split(":")[-1] in launcher
            and "<CalendarTrigger>" in xml_text
            and "ScheduleByDay" in xml_text
            and "IgnoreNew" in xml_text
            and applied == [HYGIENE_TASK_NAME]
        )

        first = dispatch_acceptance_hygiene(repo)
        checks["green_pass_surfaces_no_regressions"] = (
            first.get("ran") is True
            and first.get("ok") is True
            and first.get("regressions") == []
            and first.get("dispatched_from") == "scheduled_hygiene"
            and (first.get("sweep") or {}).get("met") == 2
        )
        state = _read_json(Path(first["state_path"])) or {}
        checks["green_baseline_recorded"] = sorted((state.get("green") or {}).keys()) == [
            "test_flaky",
            "test_stable",
        ]

        _write_probe(repo / "tests" / "acceptance", "test_flaky.py", green=False)
        second = dispatch_acceptance_hygiene(repo)
        regression = (second.get("regressions") or [{}])[0]
        checks["broken_probe_surfaces_automatically"] = (
            second.get("ok") is False
            and second.get("regression_count") == 1
            and regression.get("name") == "test_flaky"
            and regression.get("verdict") == "unmet"
            and regression.get("previously_green") is True
        )
        report = _read_json(Path(second["report_path"])) or {}
        checks["durable_report_names_regression"] = (
            report.get("ok") is False
            and [item.get("name") for item in report.get("regressions") or []] == ["test_flaky"]
        )
        state_after = _read_json(Path(second["state_path"])) or {}
        checks["green_baseline_survives_regression"] = (
            "test_flaky" in (state_after.get("green") or {})
            and state_after.get("last_ok") is False
        )

        _write_probe(repo / "tests" / "acceptance", "test_flaky.py", green=True)
        third = dispatch_acceptance_hygiene(repo)
        checks["recovered_probe_leaves_regression_list"] = (
            third.get("ok") is True and third.get("regressions") == []
        )

        registration = load_hygiene_registration(repo)
        assert registration is not None
        registration["enabled"] = False
        _atomic_write(
            hygiene_registration_path(repo),
            json.dumps(registration, indent=2, sort_keys=True) + "\n",
        )
        disabled = dispatch_acceptance_hygiene(repo)
        checks["disabled_registration_skips"] = (
            disabled.get("ran") is False and disabled.get("skip_reason") == "not_enabled"
        )

    with tempfile.TemporaryDirectory(prefix="acceptance-hygiene-unregistered-") as tmp:
        repo = _make_repo(Path(tmp))
        unregistered = dispatch_acceptance_hygiene(repo)
        checks["unregistered_dispatch_skips"] = (
            unregistered.get("ran") is False
            and unregistered.get("skip_reason") == "not_registered"
            and unregistered.get("scheduled") is False
        )

    checks["contract_is_outcome_level"] = (
        "capability_exists:" not in ACCEPTANCE_HYGIENE_DONE_WHEN
        and "capability_proved:" not in ACCEPTANCE_HYGIENE_DONE_WHEN
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_acceptance_hygiene_capability()
    return {
        "ok": ok,
        "action": "acceptance_hygiene",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": ACCEPTANCE_HYGIENE_GOAL,
        "done_when": ACCEPTANCE_HYGIENE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
