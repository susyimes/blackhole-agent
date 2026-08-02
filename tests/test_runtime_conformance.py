import subprocess

from blackhole_agent import runtime_conformance
from blackhole_agent import unbound


def test_conformance_suite_passes_against_current_controller(tmp_path):
    report = runtime_conformance.run_conformance_suite(unbound, scratch_root=tmp_path / "scratch")

    assert report["scenario_count"] == len(runtime_conformance.SCENARIOS)
    assert report["ok"] is True, [
        (s["name"], [c for c in s["checks"] if not c["ok"]]) for s in report["scenarios"] if not s["ok"]
    ]
    assert len(report["verdict_digest"]) == 64


def test_conformance_suite_falsifies_tampered_milestone_gate(tmp_path, monkeypatch):
    """A controller whose gate accepts everything must fail the suite."""

    def permissive_gate(decision, *, changed_paths, workspace=None, mission_done_when=""):
        return unbound.MilestoneGate(
            requested=decision.status in {"milestone", "complete"},
            accepted=True,
            reasons=(),
            changed_paths=tuple(changed_paths),
            behavior_paths=tuple(changed_paths),
        )

    monkeypatch.setattr(unbound, "evaluate_milestone", permissive_gate)
    report = runtime_conformance.run_conformance_suite(
        unbound,
        only=("fabricated_validation_rejected", "paperwork_milestone_rejected"),
        scratch_root=tmp_path / "scratch",
    )

    assert report["ok"] is False
    assert all(not scenario["ok"] for scenario in report["scenarios"])


def test_conformance_suite_falsifies_broken_decision_parser(tmp_path, monkeypatch):
    """A controller that mangles agent decisions must fail lifecycle scenarios."""

    monkeypatch.setattr(unbound, "extract_json_decision", lambda message: {})
    report = runtime_conformance.run_conformance_suite(
        unbound,
        only=("genesis_adopts_mission",),
        scratch_root=tmp_path / "scratch",
    )

    assert report["ok"] is False
    scenario = report["scenarios"][0]
    assert scenario["name"] == "genesis_adopts_mission"
    assert any(not check["ok"] for check in scenario["checks"])


def test_load_controller_from_candidate_path(tmp_path):
    candidate = tmp_path / "candidate_unbound.py"
    source = subprocess.run(
        ["git", "show", "HEAD:src/blackhole_agent/unbound.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidate.write_text(source, encoding="utf-8")

    module = runtime_conformance.load_controller(candidate)

    assert hasattr(module, "run_unbound_turn")
    assert hasattr(module, "evaluate_milestone")


def test_mutation_registry_covers_contract_surface():
    scenario_names = {name for name, _ in runtime_conformance.SCENARIOS}
    assert len(runtime_conformance.MUTATIONS) >= 5
    for mutation in runtime_conformance.MUTATIONS:
        assert mutation["name"]
        assert mutation["violates"]
        assert set(mutation["scenarios"]) <= scenario_names


def test_mutation_gate_catches_seeded_violations():
    fast = [
        mutation
        for mutation in runtime_conformance.MUTATIONS
        if mutation["name"] in {"broken_decision_parser", "non_durable_state", "paperwork_blind_gate"}
    ]
    report = runtime_conformance.run_mutation_gate(unbound, mutations=fast)

    assert report["ok"] is True, report["mutations"]
    assert all(mutation["caught"] for mutation in report["mutations"])
    # The controller is restored after each mutation.
    report_after = runtime_conformance.run_conformance_suite(unbound, only=("paperwork_milestone_rejected",))
    assert report_after["ok"] is True
