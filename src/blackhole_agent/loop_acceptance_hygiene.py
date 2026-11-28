"""Schedule acceptance sweeps and diagnose unmet outcomes against the last clean green release."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

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
from blackhole_agent.file_guard import atomic_write_json, atomic_write_text, file_guard
from blackhole_agent.regression_history import bisect_regression, checkout_state
from blackhole_agent.scheduled_task import task_xml

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
    src = Path(__file__).resolve().parents[1]
    return f"""import sys
from pathlib import Path
sys.path.insert(0, {str(src)!r})
from blackhole_agent.loop_acceptance_hygiene import dispatch_acceptance_hygiene
result = dispatch_acceptance_hygiene(Path({str(Path(repo_path).resolve())!r}), Path({str(Path(output_dir).resolve())!r}))
raise SystemExit(0 if result.get('ok') else 1)
"""


def render_hygiene_task_xml(registration: dict[str, Any]) -> str:
    trigger = (
        "<CalendarTrigger><StartBoundary>2000-01-01T03:00:00</StartBoundary><Enabled>true</Enabled>"
        "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"
    )
    return task_xml(registration, HYGIENE_TASK_NAME, trigger)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(durable_read_path(path).read_text(encoding="utf-8"))
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
    """Write the daily launcher and register its command with the scheduler."""

    repo = Path(repo_path)
    spec = build_hygiene_registration(repo, output_dir)
    registration_path = hygiene_registration_path(repo, output_dir)
    xml_path = hygiene_task_xml_path(repo, output_dir)
    launcher_path = hygiene_launcher_path(repo, output_dir)
    atomic_write_text(durable_write_path(launcher_path), render_hygiene_launcher(repo, registration_path.parent.parent))
    atomic_write_text(durable_write_path(xml_path), render_hygiene_task_xml(spec))
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
    atomic_write_json(durable_write_path(registration_path), recorded, ensure_ascii=True)
    applied = scheduler(recorded) if scheduler is not None else {"backend": "file", "applied": True}
    return {**recorded, **applied}


def run_acceptance_hygiene(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    timeout: int = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Compare the live sweep with prior green observations and reproduce regressions in Git."""

    repo = Path(repo_path).resolve()
    state_path = hygiene_state_path(repo, output_dir)
    target = durable_write_path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with file_guard(target):
        return _run_sweep(repo, state_path, hygiene_report_path(repo, output_dir), timeout)


def _run_sweep(repo: Path, state_path: Path, report_path: Path, timeout: int) -> dict[str, Any]:
    state = _read_json(state_path) or {"schema_version": SCHEMA_VERSION, "green": {}}
    baseline = state.get("green") if isinstance(state.get("green"), dict) else {}

    start_head, start_clean = checkout_state(repo, state_path.parent)
    sweep = sweep_acceptance_probes(repo, timeout=timeout)
    head, clean = checkout_state(repo, state_path.parent)
    stable = bool(head) and head == start_head
    deadline = time.monotonic() + timeout
    regressions: list[dict[str, Any]] = []
    green_now: dict[str, Any] = dict(baseline)
    for record in sweep.get("probes") or []:
        path = Path(record["path"]).resolve()
        name = path.stem
        previous = baseline.get(name)
        anchor = previous.get("commit") if isinstance(previous, dict) else None
        if record["exit_code"] == 0 and record["passed"] is True:
            green_now[name] = {"last_green_at": utc_now_iso(), "observed": record["observed"],
                               "commit": head if stable and clean and start_clean else anchor}
            continue
        if record.get("timed_out"):
            verdict = "timed_out"
        elif record.get("exit_code") not in (0, None):
            verdict = "crashed"
        elif record.get("passed") is False:
            verdict = "unmet"
        else:
            verdict = "invalid"
        regression = {"name": name, "verdict": verdict, "exit_code": record["exit_code"],
                      "previously_green": name in baseline, "error": record["error"]}
        if verdict == "unmet" and anchor and stable:
            regression["history"] = bisect_regression(repo, path, anchor, head, timeout=timeout, deadline=deadline)
        regressions.append(regression)
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
    atomic_write_json(durable_write_path(report_path), report, ensure_ascii=True)
    atomic_write_json(durable_write_path(state_path), {
        "schema_version": SCHEMA_VERSION, "updated_at": utc_now_iso(), "green": green_now, "last_ok": ok,
    }, ensure_ascii=True)
    return {**report, "report_path": str(report_path), "state_path": str(state_path)}


def dispatch_acceptance_hygiene(
    repo_path: Path,
    output_dir: Path | None = None,
    *,
    timeout: int = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Dispatch an enabled daily registration for this helper."""

    repo = Path(repo_path)
    registration = load_hygiene_registration(repo, output_dir)
    # Older launchers supplied the registration directory itself as the output root.
    if registration is None and output_dir is not None and output_dir.name == HYGIENE_DIR_NAME:
        legacy = _read_json(output_dir / REGISTRATION_NAME)
        if legacy and legacy.get("repo_path") == str(repo.resolve()) and legacy.get("hygiene_dir") == str(output_dir):
            registration, output_dir = legacy, output_dir.parent
    skip = {"ok": True, "ran": False, "action": "skip"}
    if registration is None:
        return {**skip, "skip_reason": "not_registered", "scheduled": False}
    if registration.get("enabled") is not True:
        return {**skip, "skip_reason": "not_enabled", "scheduled": False}
    if registration.get("trigger") != HYGIENE_TRIGGER:
        return {**skip, "skip_reason": "wrong_trigger", "scheduled": True}
    if registration.get("helper") != HYGIENE_HELPER:
        return {**skip, "skip_reason": "wrong_helper", "scheduled": True}
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
        description=ACCEPTANCE_HYGIENE_DONE_WHEN,
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


def _write_probe(path: Path, *, green: bool) -> None:
    verdict = {"passed": green, "observed": {"sentinel": "GREEN" if green else "BROKEN"}}
    path.write_text(f"print({json.dumps(verdict)!r})\n", encoding="utf-8")


def builtin_acceptance_hygiene_proof() -> dict[str, Any]:
    """Hermetic proof: scheduled hygiene surfaces probe-contract regressions."""

    import tempfile

    def matches(row: dict, **expected: Any) -> bool:
        return all(type(row.get(key)) is type(value) and row[key] == value for key, value in expected.items())

    checks = {"schema_version": SCHEMA_VERSION == 1}

    with tempfile.TemporaryDirectory(prefix="acceptance-hygiene-proof-") as tmp:
        repo = Path(tmp)
        probes = repo / "tests" / "acceptance"
        probes.mkdir(parents=True)
        flaky = probes / "test_flaky.py"
        _write_probe(probes / "test_stable.py", green=True)
        _write_probe(flaky, green=True)
        unregistered = dispatch_acceptance_hygiene(repo)
        checks["unregistered_dispatch_skips"] = matches(unregistered, ran=False, scheduled=False, skip_reason="not_registered")
        applied: list[str] = []

        def scheduler(registration: dict[str, Any]) -> dict[str, Any]:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        scheduled = schedule_acceptance_hygiene(repo, scheduler=scheduler)
        xml_text = durable_read_path(Path(scheduled["task_xml_path"])).read_text(encoding="utf-8")
        launcher = durable_read_path(Path(scheduled["launcher_path"])).read_text(encoding="utf-8")
        checks["registration_schedules_daily_sweep"] = (
            matches(scheduled, scheduled=True, ran=False, enabled=True, trigger=HYGIENE_TRIGGER, helper=HYGIENE_HELPER)
            and all(marker in xml_text for marker in ("<CalendarTrigger>", "ScheduleByDay", "IgnoreNew"))
            and HYGIENE_HELPER.split(":")[-1] in launcher and applied == [HYGIENE_TASK_NAME]
        )

        first = dispatch_acceptance_hygiene(repo)
        checks["green_pass_surfaces_no_regressions"] = (
            matches(first, ran=True, ok=True, regressions=[], dispatched_from="scheduled_hygiene")
            and matches(first.get("sweep") or {}, met=2)
        )
        state = _read_json(Path(first["state_path"])) or {}
        checks["green_baseline_recorded"] = sorted(state.get("green") or {}) == ["test_flaky", "test_stable"]

        _write_probe(flaky, green=False)
        second = dispatch_acceptance_hygiene(repo)
        regression = (second.get("regressions") or [{}])[0]
        checks["broken_probe_surfaces_automatically"] = (
            matches(second, ok=False, regression_count=1)
            and matches(regression, name="test_flaky", verdict="unmet", previously_green=True)
        )
        report = _read_json(Path(second["report_path"])) or {}
        checks["durable_report_names_regression"] = (
            report.get("ok") is False
            and [item.get("name") for item in report.get("regressions") or []] == ["test_flaky"]
        )
        state_after = _read_json(Path(second["state_path"])) or {}
        checks["green_baseline_survives_regression"] = "test_flaky" in state_after.get("green", {}) and matches(state_after, last_ok=False)

        _write_probe(flaky, green=True)
        third = dispatch_acceptance_hygiene(repo)
        checks["recovered_probe_leaves_regression_list"] = matches(third, ok=True, regressions=[])

        registration = load_hygiene_registration(repo)
        assert registration is not None
        registration["enabled"] = False
        atomic_write_json(durable_write_path(hygiene_registration_path(repo)), registration, ensure_ascii=True)
        disabled = dispatch_acceptance_hygiene(repo)
        checks["disabled_registration_skips"] = matches(disabled, ran=False, skip_reason="not_enabled")

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
