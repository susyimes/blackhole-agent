"""Tests for the autonomous capability repair plane."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    ensure_seeded_ledger,
    evaluate_outcome_contract,
)
from blackhole_agent.capability_repair import (
    FAILING_PROOF,
    detect_stale_proof_interpreter,
    diagnose_capability,
    regenerate_proof_command,
    repair_capability,
    run_repair_plane,
    verify_repair_report,
    write_repair_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_detect_stale_proof_interpreter_flags_missing_absolute() -> None:
    bogus = str(REPO_ROOT / ".blackhole-test-nonexistent" / "bin" / "python.exe")
    command = f'"{bogus}" -c "import sys; sys.exit(0)"'
    assert detect_stale_proof_interpreter(command) == bogus


def test_detect_stale_proof_interpreter_ignores_current_and_relative() -> None:
    current = f'"{sys.executable}" -c "pass"'
    assert detect_stale_proof_interpreter(current) is None
    assert detect_stale_proof_interpreter('python -c "pass"') is None
    assert detect_stale_proof_interpreter("") is None


def test_regenerate_proof_command_preserves_body() -> None:
    bogus = str(REPO_ROOT / ".blackhole-test-nonexistent" / "bin" / "python.exe")
    command = f'"{bogus}" -c "import sys; sys.exit(3)"'
    regenerated = regenerate_proof_command(command)
    assert regenerated == f'"{sys.executable}" -c "import sys; sys.exit(3)"'
    # Commands without a quoted interpreter token pass through untouched.
    assert regenerate_proof_command("echo hi") == "echo hi"


def test_diagnose_healthy_capability() -> None:
    _, ledger = ensure_seeded_ledger(REPO_ROOT)
    capability = ledger.capabilities["repo.import-health"]
    diagnosis = diagnose_capability(capability, cwd=REPO_ROOT, timeout=90)
    assert diagnosis["healthy"] is True
    assert diagnosis["failure_class"] == "none"


def test_repair_stale_interpreter_on_scratch_ledger() -> None:
    _, ledger = ensure_seeded_ledger(REPO_ROOT)
    scratch = CapabilityLedger.from_dict(ledger.to_dict())
    target = scratch.capabilities["repo.import-health"]
    bogus = str(REPO_ROOT / ".blackhole-test-nonexistent" / "Scripts" / "python.exe")
    payload = target.to_dict()
    payload["proof_command"] = f'"{bogus}"' + target.proof_command[
        target.proof_command.index('"', 1) + 1 :
    ]
    scratch.capabilities["repo.import-health"] = Capability.from_dict(payload)

    scratch, report = repair_capability(
        scratch, "repo.import-health", cwd=REPO_ROOT, timeout=90
    )
    assert report["verdict"] == "repaired"
    assert report["ok"] is True
    assert "regenerate_proof_command" in report["repair_actions"]
    assert "reprove_dependency_chain" in report["repair_actions"]
    assert scratch.capabilities["repo.import-health"].last_proof_exit_code == 0
    assert report["honest"] is True


def test_repair_unrepairable_break_fails_honestly() -> None:
    _, ledger = ensure_seeded_ledger(REPO_ROOT)
    scratch = CapabilityLedger.from_dict(ledger.to_dict())
    target = scratch.capabilities["repo.import-health"]
    payload = target.to_dict()
    payload["proof_command"] = FAILING_PROOF
    scratch.capabilities["repo.import-health"] = Capability.from_dict(payload)

    scratch, report = repair_capability(
        scratch, "repo.import-health", cwd=REPO_ROOT, timeout=90
    )
    assert report["verdict"] == "unrepairable"
    assert report["ok"] is False
    # No fake healing: the recorded proof stamp stays red.
    assert scratch.capabilities["repo.import-health"].last_proof_exit_code != 0
    assert report["honest"] is True


def test_repair_unknown_capability_is_honest() -> None:
    _, ledger = ensure_seeded_ledger(REPO_ROOT)
    _, report = repair_capability(
        ledger, "capability.does-not-exist", cwd=REPO_ROOT, timeout=30
    )
    assert report["verdict"] == "unrepairable"
    assert report["reason"] == "unknown_capability"
    assert report["honest"] is True


def test_run_repair_plane_end_to_end() -> None:
    plane = run_repair_plane(REPO_ROOT, persist=False, timeout=120)
    assert plane["action"] == "repair_plane"
    assert plane["ok"] is True
    assert plane["synthetic_repair"]["verdict"] == "repaired"
    assert "regenerate_proof_command" in plane["synthetic_repair"]["repair_actions"]
    # Falsified dependency stamps are re-proved green during repair.
    assert plane["synthetic_repair"]["falsified_dependencies"]
    assert all(
        code == 0
        for code in plane["synthetic_repair"]["dependency_stamps_after"].values()
    )
    assert plane["unrepairable_check"]["verdict"] == "unrepairable"
    assert plane["unrepairable_check"]["honest"] is True
    assert plane["contract"]["met"] is True
    assert plane["used_skill_route_discovery"] is False


def test_sealed_repair_report_verifies(tmp_path: Path) -> None:
    plane = run_repair_plane(REPO_ROOT, persist=False, timeout=120)
    write_repair_report(plane, tmp_path)
    verified = verify_repair_report(tmp_path)
    assert verified["ok"] is True
    assert all(verified["checks"].values())


def test_tampered_repair_report_fails_verification(tmp_path: Path) -> None:
    plane = run_repair_plane(REPO_ROOT, persist=False, timeout=120)
    write_repair_report(plane, tmp_path)
    sealed = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    sealed["synthetic_repair"]["verdict"] = "unrepairable"
    (tmp_path / "report.json").write_text(json.dumps(sealed, indent=2), encoding="utf-8")
    assert verify_repair_report(tmp_path)["ok"] is False


def test_missing_repair_report_fails_closed(tmp_path: Path) -> None:
    assert verify_repair_report(tmp_path)["ok"] is False


def test_repair_contract_predicates_gate_on_context() -> None:
    plane = run_repair_plane(REPO_ROOT, persist=False, timeout=120)
    contract = evaluate_outcome_contract(
        REPO_ROOT,
        "repair_plane_ok; repaired_ok; min_repair_actions:2; no_skill_route",
        context={"repair": plane},
        timeout=90,
    )
    assert contract["machine_checkable"] is True
    assert contract["met"] is True
    # A failed plane evidence payload must fail the same predicates.
    broken = dict(plane)
    broken["ok"] = False
    broken["synthetic_repair"] = {"verdict": "unrepairable", "ok": False}
    failed = evaluate_outcome_contract(
        REPO_ROOT,
        "repair_plane_ok; repaired_ok",
        context={"repair": broken},
        timeout=90,
    )
    assert failed["met"] is False


def test_growth_loop_resumes_after_autonomous_repair(tmp_path: Path, monkeypatch) -> None:
    """Proof-audit gate hands stale members to the repair plane; growth resumes."""

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
        run_growth_loop,
        save_ledger,
    )

    path, ledger = ensure_seeded_ledger(tmp_path)
    target = ledger.capabilities["capability.ledger-inventory"]
    bogus = str(tmp_path / ".nonexistent-venv" / "Scripts" / "python.exe")
    payload = target.to_dict()
    payload["proof_command"] = f'"{bogus}"' + target.proof_command[
        target.proof_command.index('"', 1) + 1 :
    ]
    payload["last_proof_exit_code"] = 0
    ledger.capabilities["capability.ledger-inventory"] = Capability.from_dict(payload)
    save_ledger(path, ledger)
    # ensure_seeded_ledger re-registers bootstrap seeds with replace=True, which
    # would restore the original proof_command; load the poisoned ledger as-is.
    monkeypatch.setattr(
        "blackhole_agent.capability_compounder.ensure_seeded_ledger",
        lambda repo_path: (
            default_ledger_path(Path(repo_path).resolve()),
            load_ledger(default_ledger_path(Path(repo_path).resolve())),
        ),
    )

    result = run_growth_loop(
        tmp_path, recipe_id="capability.composed-core-health", timeout=90
    )

    assert result["ok"] is True, result
    assert result["grew"] is True
    assert result["action"] == "promote_composition"
    after = load_ledger(path)
    repaired = after.capabilities["capability.ledger-inventory"]
    assert repaired.last_proof_exit_code == 0
    assert bogus not in repaired.proof_command
    assert "capability.composed-core-health" in after.capabilities


def test_growth_loop_honestly_halts_on_unrepairable_member(
    tmp_path: Path, monkeypatch
) -> None:
    """An always-failing member proof stays halted; the stamp stays red."""

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
        run_growth_loop,
        save_ledger,
    )

    path, ledger = ensure_seeded_ledger(tmp_path)
    target = ledger.capabilities["capability.ledger-inventory"]
    payload = target.to_dict()
    payload["proof_command"] = FAILING_PROOF
    payload["last_proof_exit_code"] = 0
    ledger.capabilities["capability.ledger-inventory"] = Capability.from_dict(payload)
    save_ledger(path, ledger)
    monkeypatch.setattr(
        "blackhole_agent.capability_compounder.ensure_seeded_ledger",
        lambda repo_path: (
            default_ledger_path(Path(repo_path).resolve()),
            load_ledger(default_ledger_path(Path(repo_path).resolve())),
        ),
    )

    result = run_growth_loop(
        tmp_path, recipe_id="capability.composed-core-health", timeout=90
    )

    assert result["ok"] is False
    assert result["grew"] is False
    assert result["action"] == "proof_audit_gate"
    assert result["reason"] == "stale_member_proofs"
    assert result["stale_members"] == ["capability.ledger-inventory"]
    assert result["repair"][0]["verdict"] == "unrepairable"
    assert result["repair"][0]["honest"] is True
    after = load_ledger(path)
    assert after.capabilities["capability.ledger-inventory"].last_proof_exit_code == 0
    assert "capability.composed-core-health" not in after.capabilities
