"""A completed repair still names its replay command after newer missions.

Newer mission files can push that repair out of a short scan. Genesis fuel
must omit the command anyway, and must still show a command that no
completed mission names.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TOKEN = "aged-repair-token"
OCCURRED_AT = "2026-11-02T01:00:00Z"
REPAIRED_AT = "2026-11-02T03:00:00Z"
NEWER_AT = "2026-11-02T04:00:00Z"


def _closer(root: Path) -> None:
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
            id="capability.validation-replay-resilience",
            name="capability.validation-replay-resilience",
            description="Proved structural closer for a harvested operational class.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    previous = Path.cwd()
    try:
        os.chdir(root)
        save_ledger(default_ledger_path(root), ledger)
    finally:
        os.chdir(previous)


def _mission(root: Path, name: str, goal: str, stamp: str, mtime: int) -> None:
    mission = root / ".blackhole-agent" / "unbound" / "missions" / name
    mission.mkdir(parents=True)
    payload = {
        "mission_id": name,
        "status": "complete",
        "created_at": stamp,
        "goal": goal,
        "last_summary": goal,
        "next_step": "None. The mission contract is met.",
    }
    path = mission / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _repo(directory: Path, *, repair: bool, newer: int) -> Path:
    from blackhole_agent.pattern_register import (
        PatternClass,
        PatternOccurrence,
        PatternRegister,
        save_register,
    )

    directory.mkdir(parents=True, exist_ok=True)
    evidence = (
        "validation replay failed: quoted command "
        f"{TOKEN} reported exit 0 but controller replay got exit 1"
    )
    entry = PatternClass(
        class_id="validation_replay_failed",
        name="validation_replay_failed",
        count=1,
        open_count=4,
        status="forced",
        structural_fix="Replay a bounded growth witness and ignore fabricated receipts.",
        occurrences=[
            PatternOccurrence(
                at=OCCURRED_AT,
                source="fixture",
                summary="turn 1 milestone rejected",
                evidence=evidence,
            )
        ],
    )
    save_register(directory, PatternRegister(classes={"validation_replay_failed": entry}))
    _closer(directory)
    base = 1_700_000_000
    if repair:
        _mission(
            directory,
            "repair-aged",
            f"Repair the quoted command {TOKEN} so controller replay matches the agent exit.",
            REPAIRED_AT,
            base,
        )
    for index in range(newer):
        _mission(
            directory,
            f"newer-{index:02d}",
            "Paint a horizontal rule in a quiet margin.",
            NEWER_AT,
            base + 60 + index,
        )
    return directory


def observe() -> tuple[bool, dict]:
    from blackhole_agent.failure_class_growth import (
        SCAN_LIMIT,
        render_unclassified_growth_for_genesis,
    )

    newer = int(SCAN_LIMIT)
    with tempfile.TemporaryDirectory(prefix="bh-aged-repair-") as directory:
        base = Path(directory)
        repaired = _repo(base / "repaired", repair=True, newer=newer)
        bare = _repo(base / "bare", repair=False, newer=newer)
        repaired_text = render_unclassified_growth_for_genesis(repaired)
        bare_text = render_unclassified_growth_for_genesis(bare)
    observed = {
        "newer_missions": newer,
        "repaired_omits_command": TOKEN not in repaired_text,
        "repaired_text": repaired_text[:240],
        "unrepaired_shows_command": TOKEN in bare_text,
        "unrepaired_text": bare_text[:240],
    }
    passed = bool(observed["repaired_omits_command"] and observed["unrepaired_shows_command"])
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:500]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
