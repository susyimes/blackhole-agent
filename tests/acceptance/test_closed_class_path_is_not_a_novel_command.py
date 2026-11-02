"""A checkout path is not an unseen replay command.

Genesis fuel was still naming the harvested ruff invocation after that
PowerShell call operator already replayed. The only tokens outside the proved
closer were directory segments of this checkout. A directory segment stays
off the card. A leaf filename and a command word outside any path stay on it.
A covered command, a later repair, a selection-gate rejection, and an open
class stay off it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED = (
    "validation replay failed: & "
    "'C:\\Users\\svmes\\Documents\\Playground\\blackhole-agent\\.venv\\Scripts\\python.exe' "
    "-m ruff check src\\blackhole_agent\\failure_class_growth.py "
    "tests\\acceptance\\test_closed_class_novel_symptom.py "
    "reported exit 0 but controller replay got exit 1"
)
DIRECTORY = (
    "validation replay failed: & 'C:\\tools\\archivemarker\\python.exe' -m ruff "
    "reported exit 0 but controller replay got exit 1"
)
LEAF = (
    "validation replay failed: & 'C:\\tools\\uniquenode.exe' -m ruff "
    "reported exit 0 but controller replay got exit 1"
)
WORD = (
    "validation replay failed: quoted command leafmarker "
    "reported exit 0 but controller replay got exit 1"
)
COVERED = "fabricated-exit-code"
REPAIRED = "repaired-slot-88"
GATE = "marginal-gate-token"
OPEN = "open-class-slot-55"
OCCURRED_AT = "2026-11-02T01:00:00Z"
REPAIRED_AT = "2026-11-02T03:00:00Z"
STRUCTURAL_FIX = "Replay a bounded growth witness and ignore fabricated receipts."


def _closer(ledger_ready: bool, capability_id: str) -> None:
    if not ledger_ready:
        return
    from blackhole_agent.capability_compounder import (
        Capability,
        CapabilityLedger,
        default_ledger_path,
        register_capability,
        save_ledger,
    )

    ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved structural closer for a harvested operational class.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(default_ledger_path(Path.cwd()), ledger)


def _repo(
    directory: Path,
    *,
    class_id: str,
    evidence: str,
    capability_id: str,
    closed: bool,
    structural_fix: str = STRUCTURAL_FIX,
    repair_goal: str = "",
) -> Path:
    from blackhole_agent.pattern_register import (
        PatternClass,
        PatternOccurrence,
        PatternRegister,
        save_register,
    )

    root = directory
    entry = PatternClass(
        class_id=class_id,
        name=class_id,
        count=1,
        open_count=4,
        status="forced",
        structural_fix=structural_fix,
        occurrences=[
            PatternOccurrence(
                at=OCCURRED_AT,
                source="fixture",
                summary="turn 1 milestone rejected",
                evidence=evidence,
            )
        ],
    )
    save_register(root, PatternRegister(classes={class_id: entry}))
    if repair_goal:
        mission = root / ".blackhole-agent" / "unbound" / "missions" / "repair-1"
        mission.mkdir(parents=True)
        payload = {
            "mission_id": "repair-1",
            "status": "complete",
            "created_at": REPAIRED_AT,
            "goal": repair_goal,
            "last_summary": repair_goal,
            "next_step": "None. The mission contract is met.",
        }
        (mission / "state.json").write_text(json.dumps(payload), encoding="utf-8")
    original = Path.cwd()
    try:
        import os

        os.chdir(root)
        _closer(closed, capability_id)
    finally:
        os.chdir(original)
    return root


def _render(root: Path) -> str:
    from blackhole_agent.failure_class_growth import render_unclassified_growth_for_genesis

    return render_unclassified_growth_for_genesis(root)


def observe() -> tuple[bool, dict]:
    with tempfile.TemporaryDirectory(prefix="bh-path-symptom-") as directory:
        base = Path(directory)
        harvested = _repo(
            base / "harvested",
            class_id="validation_replay_failed",
            evidence=HARVESTED,
            capability_id="capability.validation-replay-resilience",
            closed=True,
        )
        directory_only = _repo(
            base / "directory",
            class_id="validation_replay_failed",
            evidence=DIRECTORY,
            capability_id="capability.validation-replay-resilience",
            closed=True,
        )
        leaf = _repo(
            base / "leaf",
            class_id="validation_replay_failed",
            evidence=LEAF,
            capability_id="capability.validation-replay-resilience",
            closed=True,
        )
        word = _repo(
            base / "word",
            class_id="validation_replay_failed",
            evidence=WORD,
            capability_id="capability.validation-replay-resilience",
            closed=True,
        )
        covered = _repo(
            base / "covered",
            class_id="validation_replay_failed",
            evidence=(
                "validation replay failed: "
                f"{COVERED} reported exit 0 but controller replay got exit 1"
            ),
            structural_fix=f"The closer already names {COVERED} and replays that command.",
            capability_id="capability.validation-replay-resilience",
            closed=True,
        )
        repaired = _repo(
            base / "repaired",
            class_id="validation_replay_failed",
            evidence=(
                "validation replay failed: quoted command "
                f"{REPAIRED} reported exit 0 but controller replay got exit 1"
            ),
            capability_id="capability.validation-replay-resilience",
            closed=True,
            repair_goal=(
                f"Repair the quoted command {REPAIRED} so controller replay matches the agent exit."
            ),
        )
        gate = _repo(
            base / "gate",
            class_id="milestone_rejected",
            evidence=f"marginal_value_gate: score 1 is below 2 {GATE}",
            structural_fix="Stage porcelain paths and skip regenerable extracts.",
            capability_id="capability.milestone-commit-resilience",
            closed=True,
        )
        opened = _repo(
            base / "open",
            class_id="validation_replay_failed",
            evidence=(
                "validation replay failed: quoted command "
                f"{OPEN} reported exit 0 but controller replay got exit 1"
            ),
            capability_id="capability.validation-replay-resilience",
            closed=False,
        )
        rendered = {
            "harvested": _render(harvested),
            "directory": _render(directory_only),
            "leaf": _render(leaf),
            "word": _render(word),
            "covered": _render(covered),
            "repaired": _render(repaired),
            "gate": _render(gate),
            "open": _render(opened),
        }
    harvested_text = rendered["harvested"].casefold()
    observed = {
        "harvested_has_playground": "playground" in harvested_text,
        "harvested_has_checkout": "blackhole-agent" in harvested_text,
        "directory_has_marker": "archivemarker" in rendered["directory"].casefold(),
        "leaf_has_marker": "uniquenode" in rendered["leaf"].casefold(),
        "word_has_marker": "leafmarker" in rendered["word"].casefold(),
        "covered_has_marker": COVERED in rendered["covered"],
        "repaired_has_marker": REPAIRED in rendered["repaired"],
        "gate_has_marker": GATE in rendered["gate"],
        "open_has_marker": OPEN in rendered["open"],
        "harvested_text": rendered["harvested"][:240],
    }
    passed = (
        observed["harvested_has_playground"] is False
        and observed["harvested_has_checkout"] is False
        and observed["directory_has_marker"] is False
        and observed["leaf_has_marker"] is True
        and observed["word_has_marker"] is True
        and observed["covered_has_marker"] is False
        and observed["repaired_has_marker"] is False
        and observed["gate_has_marker"] is False
        and observed["open_has_marker"] is False
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
