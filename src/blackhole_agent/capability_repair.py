"""Autonomous capability repair plane.

The fitness gate and the ledger proof re-audit can *measure* a stale or broken
capability, but measurement alone only halts growth with ``repair_needed``.
This module closes that gap into autonomous repair:

- diagnose a capability proof (stale interpreter path, import error, replay
  failure) without trusting its self-attested stamp,
- execute a bounded deterministic repair: regenerate the proof-command
  interpreter path, then re-prove the full dependency chain,
- verify the repair by an actual green re-proof — never by declaration,
- adversarially falsify the repair path itself: a synthetic stale-interpreter
  break must heal, and an unrepairable break must be reported honestly with
  the recorded proof stamp left red (no fake healing).

Synthetic breaks run on deep-copied scratch ledgers; the live ledger is only
mutated for explicitly requested live repairs and is persisted by the caller.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from blackhole_agent.durable_state import durable_read_path, durable_write_path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    ensure_seeded_ledger,
    evaluate_outcome_contract,
    legacy_pipeline_was_used,
    portable_proof_command,
    prove_capability,
    run_capability,
    save_ledger,
    utc_now_iso,
)

__all__ = [
    "builtin_repair_plane",
    "detect_stale_proof_interpreter",
    "diagnose_capability",
    "regenerate_proof_command",
    "repair_capability",
    "run_repair_plane",
    "verify_repair_report",
    "write_repair_report",
]

# Proof commands persist in the portable form `uv run python -c "..."`.
# Historical ledgers recorded `"<sys.executable>" -c "..."`; when such an
# absolute interpreter path travels between checkouts, worktrees, or machines
# it can cease to exist — every proof replay then fails even though the
# capability itself is healthy. Repair rebinds those commands to the portable
# form rather than to another machine-local path.
_INTERPRETER_PATTERN = re.compile(r'^\s*"(?P<exe>[^"]+)"')

_PORTABLE_PROOF_PREFIX = "uv run python"

_IMPORT_ERROR_MARKERS = (
    "ModuleNotFoundError",
    "ImportError",
    "No module named",
)

FAILING_PROOF = f'"{sys.executable}" -c "import sys; sys.exit(1)"'

DEFAULT_REPAIR_TARGET = "capability.ledger-inventory"

REPAIR_CONTRACT = (
    "repair_plane_ok; repaired_ok; min_repair_actions:2; "
    "capability_exists:repo.import-health; no_skill_route"
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _clone_ledger(ledger: CapabilityLedger) -> CapabilityLedger:
    """Deep-copy a ledger for non-destructive repair experiments."""

    return CapabilityLedger.from_dict(ledger.to_dict())


def _replace_capability_fields(
    ledger: CapabilityLedger,
    capability_id: str,
    **overrides: Any,
) -> CapabilityLedger:
    """Replace selected fields on one capability (scratch or live ledger)."""

    original = ledger.capabilities.get(capability_id)
    if original is None:
        raise KeyError(capability_id)
    payload = original.to_dict()
    payload.update(overrides)
    ledger.capabilities[capability_id] = Capability.from_dict(payload)
    ledger.updated_at = utc_now_iso()
    return ledger


def _swap_proof_interpreter(command: str, executable: str) -> str:
    """Replace the interpreter a proof command runs through.

    Handles both the historical quoted-interpreter form and the portable
    ``uv run python`` form; the result always uses the quoted-interpreter
    form so callers can plant arbitrary (including nonexistent) interpreter
    paths for falsification experiments.
    """

    text = command or ""
    match = _INTERPRETER_PATTERN.match(text)
    if match is not None:
        return f'"{executable}"' + text[match.end() :]
    stripped = text.lstrip()
    if stripped.startswith(_PORTABLE_PROOF_PREFIX):
        return f'"{executable}"' + stripped[len(_PORTABLE_PROOF_PREFIX) :]
    return text


def detect_stale_proof_interpreter(
    command: str,
    *,
    executable: str | None = None,
) -> str | None:
    """Return the recorded interpreter path when it no longer exists locally.

    A recorded path that differs from the current interpreter but still exists
    is portable enough to replay and is not flagged. Only absolute paths that
    have ceased to exist are stale.
    """

    current = executable or sys.executable
    match = _INTERPRETER_PATTERN.match(command or "")
    if match is None:
        return None
    recorded = match.group("exe")
    if recorded == current:
        return None
    recorded_path = Path(recorded)
    if not recorded_path.is_absolute():
        return None
    if recorded_path.exists():
        return None
    return recorded


def regenerate_proof_command(
    command: str,
    *,
    executable: str | None = None,
) -> str:
    """Rebind a proof command to a working interpreter, keeping the body.

    Python proofs are rebound to the portable ``uv run python`` form so a
    repaired ledger entry stays machine-independent; non-Python commands fall
    back to swapping in the current interpreter path.
    """

    rebound = portable_proof_command(command)
    if rebound != (command or "") or (command or "").lstrip().startswith(_PORTABLE_PROOF_PREFIX):
        return rebound
    return _swap_proof_interpreter(command, executable or sys.executable)


def diagnose_capability(
    capability: Capability,
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
) -> dict[str, Any]:
    """Replay a capability proof and classify the failure mode.

    The replay goes through the recorded ``proof_command`` (the same surface
    ``prove_capability`` uses), never the capability's self-attested stamp.
    """

    stale = detect_stale_proof_interpreter(capability.proof_command)
    replay = run_capability(
        capability,
        cwd=cwd,
        command_runner=command_runner,
        timeout=timeout,
        use_proof=True,
    )
    combined = f"{replay.stdout}\n{replay.stderr}"
    if replay.ok and stale is None:
        failure_class = "none"
    elif stale is not None:
        failure_class = "stale_proof_interpreter"
    elif any(marker in combined for marker in _IMPORT_ERROR_MARKERS):
        failure_class = "import_error"
    else:
        failure_class = "proof_replay_failed"
    return {
        "capability_id": capability.id,
        "ok": replay.ok,
        "healthy": replay.ok and stale is None,
        "failure_class": failure_class,
        "stale_interpreter": stale,
        "replay": replay.to_dict(),
    }


def repair_capability(
    ledger: CapabilityLedger,
    capability_id: str,
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    skip_proved_deps: bool = False,
) -> tuple[CapabilityLedger, dict[str, Any]]:
    """Diagnose then repair one capability inside ``ledger``.

    Repair is bounded and deterministic: regenerate a stale proof-command
    interpreter, then re-prove the whole dependency chain
    (``skip_proved_deps=False``) so stale dependency stamps are re-verified
    rather than trusted. The verdict is ``healthy`` (nothing to do),
    ``repaired`` (green re-proof after repair), or ``unrepairable`` (honest
    failure; the recorded proof stamp is left non-green).
    """

    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        return ledger, {
            "capability_id": capability_id,
            "ok": False,
            "verdict": "unrepairable",
            "reason": "unknown_capability",
            "repair_actions": [],
            "honest": True,
        }

    diagnosis = diagnose_capability(
        capability,
        cwd=cwd,
        command_runner=command_runner,
        timeout=timeout,
    )
    if diagnosis["healthy"] and capability.last_proof_exit_code == 0:
        return ledger, {
            "capability_id": capability_id,
            "ok": True,
            "verdict": "healthy",
            "repair_actions": [],
            "diagnosis": diagnosis,
            "honest": True,
        }

    actions: list[str] = []
    if diagnosis["healthy"] and capability.last_proof_exit_code != 0:
        actions.append("reprove_stale_stamp")
    if diagnosis["stale_interpreter"] is not None:
        ledger = _replace_capability_fields(
            ledger,
            capability_id,
            proof_command=regenerate_proof_command(capability.proof_command),
        )
        actions.append("regenerate_proof_command")

    ledger, proof = prove_capability(
        ledger,
        capability_id,
        cwd=cwd,
        command_runner=command_runner,
        timeout=timeout,
        skip_proved_deps=skip_proved_deps,
    )
    actions.append("reprove_dependency_chain")

    final = ledger.capabilities[capability_id]
    verdict = "repaired" if proof.ok else "unrepairable"
    # Honesty: the recorded stamp must match the actual re-proof outcome.
    honest = (final.last_proof_exit_code == 0) is proof.ok
    return ledger, {
        "capability_id": capability_id,
        "ok": proof.ok,
        "verdict": verdict,
        "repair_actions": actions,
        "diagnosis": diagnosis,
        "proof": proof.to_dict(),
        "last_proof_exit_code": final.last_proof_exit_code,
        "honest": honest,
    }


def write_repair_report(report: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write a digest-sealed repair report into ``output_dir``."""

    output_dir = durable_write_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in report.items() if key != "payload_digest"}
    sealed = dict(payload)
    sealed["payload_digest"] = _digest(payload)
    text = json.dumps(sealed, indent=2, sort_keys=True, default=str)
    (output_dir / "report.json").write_text(text + "\n", encoding="utf-8")
    stamp = str(report.get("generated_at") or utc_now_iso()).replace(":", "-")
    (output_dir / f"repair-{stamp}.json").write_text(text + "\n", encoding="utf-8")
    return {
        "ok": True,
        "report_dir": str(output_dir),
        "payload_digest": sealed["payload_digest"],
    }


def verify_repair_report(report_dir: Path) -> dict[str, Any]:
    """Re-check a sealed repair report: digest plus phase verdicts."""

    path = report_dir / "report.json"
    if not path.exists():
        return {"ok": False, "error": "missing report.json", "checks": {}}
    try:
        sealed = json.loads(durable_read_path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return {"ok": False, "error": f"invalid report.json: {error}", "checks": {}}
    payload = {key: value for key, value in sealed.items() if key != "payload_digest"}
    checks = {
        "digest_matches": _digest(payload) == sealed.get("payload_digest"),
        "synthetic_repaired": (sealed.get("synthetic_repair") or {}).get("verdict")
        == "repaired",
        "unrepairable_honest": (sealed.get("unrepairable_check") or {}).get("honest")
        is True,
        "no_skill_route": not sealed.get("used_skill_route_discovery"),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "report_dir": str(report_dir),
    }


def run_repair_plane(
    repo_path: Path,
    *,
    target_id: str = DEFAULT_REPAIR_TARGET,
    live_ids: Sequence[str] = (),
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    persist: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    """Closed repair plane: diagnose → repair → verify → adversarial falsify.

    Phases:

    1. live repairs — explicitly requested live members are repaired in place
       and the live ledger is persisted (bounded to ``live_ids``),
    2. synthetic repair — a scratch clone gets a stale proof-command
       interpreter plus a falsified dependency stamp; repair must regenerate
       the command, re-prove the dependency chain, and end green,
    3. unrepairable falsification — a scratch clone gets an always-failing
       proof; repair must verdict ``unrepairable`` and leave the stamp red,
    4. outcome contract — ``repair_plane_ok; repaired_ok;
       min_repair_actions:2`` machine-checked against the plane evidence.
    """

    root = repo_path.resolve()
    path, live = ensure_seeded_ledger(root)
    if target_id not in live.capabilities:
        return {
            "ok": False,
            "action": "repair_plane",
            "error": f"unknown repair target {target_id}",
            "ledger_path": str(path),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }

    # Phase 1: bounded live repairs (explicit ids only).
    working = live
    live_repairs: list[dict[str, Any]] = []
    for capability_id in live_ids:
        working, report = repair_capability(
            working,
            str(capability_id),
            cwd=root,
            command_runner=command_runner,
            timeout=timeout,
        )
        live_repairs.append(report)
    if persist and live_repairs:
        save_ledger(path, working)
    live_ok = all(item.get("ok") for item in live_repairs)

    # Phase 2: synthetic stale-interpreter break + falsified dependency stamp.
    target = working.capabilities[target_id]
    bogus_interpreter = str(
        root / ".blackhole-repair-nonexistent" / "Scripts" / "python.exe"
    )
    scratch = _clone_ledger(working)
    scratch = _replace_capability_fields(
        scratch,
        target_id,
        proof_command=_swap_proof_interpreter(
            target.proof_command, bogus_interpreter
        ),
        last_proof_exit_code=0,
        last_proved_at=utc_now_iso(),
    )
    falsified_deps: list[str] = []
    for dependency in target.dependencies:
        if dependency in scratch.capabilities:
            scratch = _replace_capability_fields(
                scratch,
                dependency,
                last_proof_exit_code=1,
                last_proved_at="",
            )
            falsified_deps.append(dependency)
    scratch, synthetic_report = repair_capability(
        scratch,
        target_id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
    )
    dep_stamps = {
        dependency: scratch.capabilities[dependency].last_proof_exit_code
        for dependency in falsified_deps
    }
    synthetic_repaired = (
        synthetic_report.get("verdict") == "repaired"
        and bool(synthetic_report.get("ok"))
        and "regenerate_proof_command" in synthetic_report.get("repair_actions", [])
        and all(code == 0 for code in dep_stamps.values())
    )
    synthetic_phase = {
        **synthetic_report,
        "bogus_interpreter": bogus_interpreter,
        "falsified_dependencies": falsified_deps,
        "dependency_stamps_after": dep_stamps,
    }

    # Phase 3: unrepairable break must fail honestly (stamp stays red).
    unrepairable_scratch = _clone_ledger(working)
    unrepairable_scratch = _replace_capability_fields(
        unrepairable_scratch,
        target_id,
        proof_command=FAILING_PROOF,
        last_proof_exit_code=0,
        last_proved_at=utc_now_iso(),
    )
    unrepairable_scratch, unrepairable_report = repair_capability(
        unrepairable_scratch,
        target_id,
        cwd=root,
        command_runner=command_runner,
        timeout=timeout,
    )
    unrepairable_stamp = unrepairable_scratch.capabilities[target_id].last_proof_exit_code
    unrepairable_honest = (
        unrepairable_report.get("verdict") == "unrepairable"
        and not unrepairable_report.get("ok")
        and unrepairable_stamp != 0
        and bool(unrepairable_report.get("honest"))
    )
    unrepairable_phase = {
        **unrepairable_report,
        "stamp_after": unrepairable_stamp,
        "honest": unrepairable_honest,
    }

    repair_action_count = len(synthetic_report.get("repair_actions") or []) + sum(
        len(item.get("repair_actions") or []) for item in live_repairs
    )

    result: dict[str, Any] = {
        "ok": False,  # finalized after contract evaluation
        "action": "repair_plane",
        "target_id": target_id,
        "live_repairs": live_repairs,
        "synthetic_repair": synthetic_phase,
        "unrepairable_check": unrepairable_phase,
        "repair_action_count": repair_action_count,
        "generated_at": utc_now_iso(),
        "ledger_path": str(path),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }

    core_ok = (
        live_ok
        and synthetic_repaired
        and unrepairable_honest
        and not result["used_skill_route_discovery"]
    )
    result["ok"] = bool(core_ok)

    # Phase 4: outcome contract against the plane evidence.
    contract = evaluate_outcome_contract(
        root,
        REPAIR_CONTRACT,
        context={"repair": result, "repair_plane": result},
        command_runner=command_runner,
        timeout=timeout,
    )
    result["contract"] = contract
    result["ok"] = bool(core_ok and contract.get("met") is True)

    if persist:
        out_dir = (
            report_dir.resolve()
            if report_dir is not None
            else root / "artifacts" / "capability-repair"
        )
        result["report"] = write_repair_report(result, out_dir)
        result["report_verify"] = verify_repair_report(out_dir)
        result["ok"] = bool(result["ok"] and result["report_verify"].get("ok"))

    return result


def builtin_repair_plane() -> dict[str, Any]:
    """Invocable capability: diagnose → repair → verify → adversarial falsify."""

    root = Path(__file__).resolve().parents[2]
    target_id = (os.environ.get("BLACKHOLE_REPAIR_TARGET") or "").strip() or (
        DEFAULT_REPAIR_TARGET
    )
    persist = (os.environ.get("BLACKHOLE_REPAIR_PERSIST") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    report_raw = (os.environ.get("BLACKHOLE_REPAIR_REPORT_DIR") or "").strip()
    report_dir = Path(report_raw) if report_raw else None
    live_raw = (os.environ.get("BLACKHOLE_REPAIR_LIVE_IDS") or "").strip()
    live_ids = tuple(item.strip() for item in live_raw.split(",") if item.strip())
    return run_repair_plane(
        root,
        target_id=target_id,
        live_ids=live_ids,
        persist=persist,
        report_dir=report_dir,
        timeout=180,
    )
