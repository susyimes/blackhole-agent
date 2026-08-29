import json
import os
from pathlib import Path

from blackhole_agent.mission_selection import (
    DIVERSITY_SATURATION_COUNT,
    assess_mission_selection,
    capability_family,
    render_mission_selection_guard,
    semantic_signature,
)


def _depth_goal(level: int) -> str:
    return (
        "Optional later work is reflecting Python nested-namespace class instance methods "
        f"{level} submodule levels down so sdists whose covering API is a {level}-level nested "
        f"Class().method instance rather than a {level - 1}-level nested Class().method instance "
        "can be foraged the same way."
    )


def _write_history(repo: Path, mission_id: str, goal: str, *, order: int) -> None:
    state_path = repo / ".blackhole-agent" / "unbound" / "missions" / mission_id / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "status": "complete",
                "goal": goal,
                "done_when": "A runnable behavior is proved.",
                "recent_turns": [],
            }
        ),
        encoding="utf-8",
    )
    os.utime(state_path, (order, order))


def test_numeric_depth_changes_have_one_semantic_signature_and_family() -> None:
    assert semantic_signature(_depth_goal(151)) == semantic_signature(_depth_goal(152))
    assert capability_family(_depth_goal(151)) == capability_family(_depth_goal(152))


def test_selection_rejects_repetition_low_marginal_value_and_saturated_family(tmp_path: Path) -> None:
    for index, level in enumerate(range(145, 151), start=1):
        _write_history(tmp_path, f"mission-{level}", _depth_goal(level), order=index)

    gate = assess_mission_selection(
        tmp_path,
        _depth_goal(151),
        "The next depth-specific fixture passes.",
    )

    assert gate.accepted is False
    assert gate.repetition_count >= 1
    assert gate.scalar_extension is True
    assert gate.recent_family_count >= DIVERSITY_SATURATION_COUNT
    assert any(reason.startswith("repetition_gate:") for reason in gate.reasons)
    assert any(reason.startswith("marginal_value_gate:") for reason in gate.reasons)
    assert any(reason.startswith("capability_diversity_gate:") for reason in gate.reasons)


def test_selection_accepts_materially_different_measurable_repair(tmp_path: Path) -> None:
    for index, level in enumerate(range(145, 151), start=1):
        _write_history(tmp_path, f"mission-{level}", _depth_goal(level), order=index)

    gate = assess_mission_selection(
        tmp_path,
        "Replace fragile publication retries with an idempotent end-to-end recovery protocol.",
        "A simulated failed push recovers exactly once and remote lineage remains correct.",
    )

    assert gate.accepted is True
    assert gate.marginal_value_score >= 2
    assert gate.capability_family != capability_family(_depth_goal(151))


def test_selection_rejects_vacuous_goal_but_operator_override_still_wins(tmp_path: Path) -> None:
    rejected = assess_mission_selection(tmp_path, "Mission complete", "The task is done.")
    operator = assess_mission_selection(
        tmp_path,
        "Fix auth",
        "The operator-requested authentication path succeeds.",
        forced=True,
    )

    assert rejected.accepted is False
    assert any(reason.startswith("marginal_value_gate:") for reason in rejected.reasons)
    assert operator.accepted is True


def test_genesis_guard_surfaces_all_three_hard_gates(tmp_path: Path) -> None:
    for index, level in enumerate(range(145, 151), start=1):
        _write_history(tmp_path, f"mission-{level}", _depth_goal(level), order=index)

    guard = render_mission_selection_guard(tmp_path)

    assert "Repetition" in guard
    assert "Marginal value" in guard
    assert "Capability diversity" in guard
    assert capability_family(_depth_goal(151)) in guard
