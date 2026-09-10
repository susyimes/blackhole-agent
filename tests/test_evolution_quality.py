import json
from types import SimpleNamespace

import pytest

from blackhole_agent.evolution_quality import (
    LOCAL_NO_PROGRESS_LIMIT,
    behavior_family,
    content_fingerprint,
    find_renamed_implementations,
    ledger_only_contract,
    record_local_progress,
)
from blackhole_agent.mission_selection import MissionHistoryEntry, assess_mission_selection, semantic_signature
from blackhole_agent.unbound import KernelTurnResult, load_mission, run_unbound_turn, save_mission
from tests.test_unbound import decision_payload, git_head, init_repository, make_state


def protocol_goal(name):
    return (
        f"Repair {name} unsupported handshake; a missing {name}id is forbidden, "
        f"seal a {name}digest and independently poll it on a later reader."
    )


def test_protocol_renaming_cannot_buy_diversity(tmp_path):
    history = [
        MissionHistoryEntry(str(i), protocol_goal(name), semantic_signature(protocol_goal(name)), name, "complete")
        for i, name in enumerate(("bgp4", "pmsi", "wildad"))
    ]
    goal = protocol_goal("never_seen_protocol")
    gate = assess_mission_selection(tmp_path, goal, "An interoperability fixture succeeds.", history=history)
    assert not gate.accepted
    assert gate.repetition_count == 3 and gate.recent_family_count == 3
    assert behavior_family(goal) == "network/handshake-digest-demo"


def test_real_network_repair_is_not_blanket_banned(tmp_path):
    gate = assess_mission_selection(
        tmp_path,
        "Repair TCP stream reassembly with split packets and retransmission.",
        "Captured reference packets reconstruct the exact application payload.",
    )
    assert gate.accepted


def test_inventory_contract_is_not_new_capability_acceptance(tmp_path):
    contract = "capability_exists:capability.new;capability_proved:capability.new;no_skill_route"
    assert ledger_only_contract(contract)
    assert not ledger_only_contract(contract + "; A reference peer accepts the wire frame.")
    assert not assess_mission_selection(tmp_path, "Repair a missing protocol behavior", contract).accepted
    assert assess_mission_selection(tmp_path, "Inspect ledger health", contract, forced=True).accepted


def test_fingerprint_measures_contents_not_existing_dirty_paths(tmp_path):
    (tmp_path / "src").mkdir()
    file = tmp_path / "src" / "seed.py"
    file.write_text("VALUE = 1")
    paths = ["src/seed.py", "capabilities/ledger.json"]
    before = content_fingerprint(tmp_path, paths)
    (tmp_path / "capabilities").mkdir()
    (tmp_path / "capabilities" / "ledger.json").write_text('{"updated_at":"now"}')
    assert content_fingerprint(tmp_path, paths) == before
    file.write_text("VALUE = 2")
    assert content_fingerprint(tmp_path, paths) != before
    file.unlink()
    assert content_fingerprint(tmp_path, paths) != before


def test_watchdog_bound_and_real_progress_reset():
    state = SimpleNamespace(local_no_progress_count=0)
    for _ in range(LOCAL_NO_PROGRESS_LIMIT):
        result = record_local_progress(state, kernel="local", before="same", after="same", milestone=False)
    assert result["blocked"]
    result = record_local_progress(state, kernel="local", before="same", after="changed", milestone=False)
    assert not result["blocked"] and state.local_no_progress_count == 0


def test_ast_clone_gate_ignores_names_but_keeps_control_flow(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    source = "\n".join(f"def old_{i}(x):\n    if x:\n        return x + {i}\n    return 0\n" for i in range(15))
    (root / "old.py").write_text(source)
    (root / "renamed.py").write_text(source.replace("old_", "brand_new_").replace(" x", " y"))
    assert find_renamed_implementations(tmp_path, ["src/renamed.py"])
    (root / "renamed.py").write_text("def different(items):\n    return [x for x in items if x]\n")
    assert not find_renamed_implementations(tmp_path, ["src/renamed.py"])


def setup_turn(tmp_path):
    init_repository(tmp_path)
    state = make_state(tmp_path, base_head=git_head(tmp_path), last_milestone_head=git_head(tmp_path))
    path = tmp_path / ".blackhole-agent" / "unbound" / "missions" / "mission-1" / "state.json"
    path.parent.mkdir(parents=True)
    save_mission(path, state)
    return path


def fake_salvage(payload):
    from blackhole_agent.unbound import TurnDecision

    def execute(state, prompt, turn_dir, **kwargs):
        result = KernelTurnResult("local", payload, "local", ("local",), "")
        return result, TurnDecision.from_payload(json.loads(payload)), {}

    return execute


def test_watchdog_persists_and_blocks_without_losing_dirty_work(tmp_path, monkeypatch):
    path = setup_turn(tmp_path)
    (tmp_path / "src" / "seed.py").write_text("VALUE = 22\n")
    monkeypatch.setattr("blackhole_agent.unbound.hydrate_mission_from_campaign", lambda *a, **k: {})
    monkeypatch.setattr(
        "blackhole_agent.unbound.execute_kernel_turn_with_salvage", fake_salvage(decision_payload("continue"))
    )
    for _ in range(LOCAL_NO_PROGRESS_LIMIT):
        result = run_unbound_turn(path)
    assert result["effective_status"] == "blocked"
    assert load_mission(path).local_no_progress_count == LOCAL_NO_PROGRESS_LIMIT
    assert "no behavior-content progress" in load_mission(path).last_error
    assert (tmp_path / "src" / "seed.py").read_text() == "VALUE = 22\n"


def test_local_cannot_weaken_bound_contract_to_inventory(tmp_path, monkeypatch):
    path = setup_turn(tmp_path)
    original = load_mission(path).done_when
    payload = decision_payload(
        "complete",
        done_when="mission_plane_ok;no_skill_route",
        done_when_met=True,
        capability_delta="Ran ledger inventory",
        outcome_evidence=["inventory ok"],
    )
    monkeypatch.setattr("blackhole_agent.unbound.hydrate_mission_from_campaign", lambda *a, **k: {})
    monkeypatch.setattr("blackhole_agent.unbound.execute_kernel_turn_with_salvage", fake_salvage(payload))
    result = run_unbound_turn(path)
    assert result["effective_status"] == "continue"
    assert load_mission(path).done_when == original
    assert any("bound done_when" in reason for reason in result["milestone_gate"]["reasons"])


@pytest.mark.parametrize("stage", ["execution", "genesis"])
def test_auto_prebound_goal_does_not_inherit_operator_override(tmp_path, monkeypatch, stage):
    path = setup_turn(tmp_path)
    state = load_mission(path)
    state.goal, state.done_when, state.stage = protocol_goal("foo"), "capability_proved:capability.foo", stage
    save_mission(path, state)
    monkeypatch.setattr("blackhole_agent.unbound.hydrate_mission_from_campaign", lambda *a, **k: {})
    monkeypatch.setattr(
        "blackhole_agent.unbound.execute_kernel_turn_with_salvage", fake_salvage(decision_payload("continue"))
    )
    result = run_unbound_turn(path)
    assert not result["selection_gate"]["accepted"]
    assert not load_mission(path).selection_checked
