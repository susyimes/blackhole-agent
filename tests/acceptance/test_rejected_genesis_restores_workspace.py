"""A rejected genesis turn must not leave its edit for the next milestone.

Harvested mission 20261030T005435Z-1557230e kept a refused controller-adoption
edit in the workspace after selection failed, so the next accepted milestone
would have published it. Prints JSON with boolean passed and nonempty
observed. Exit 0 for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _decision(status: str, **overrides: object) -> str:
    payload = {
        "status": status,
        "mission_goal": "",
        "done_when": "",
        "summary": "Submitted a genesis decision.",
        "strategy": "Exercise the workspace after selection.",
        "next_step": "Read the files the turn left behind.",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "done_when_met": False,
        "commit_message": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import KernelTurnResult, UnboundMission, run_unbound_turn, save_mission

    with tempfile.TemporaryDirectory(prefix="bh-rejected-genesis-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "probe@example.invalid")
        _git(repo, "config", "user.name", "probe")
        (repo / "src").mkdir()
        (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
        (repo / "src" / "other.py").write_text("OTHER = 1\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "seed")
        venv = repo / ".venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("keep-venv\n", encoding="utf-8")
        outside = root / "outside.txt"
        outside.write_text("keep-outside\n", encoding="utf-8")
        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        state_path = root / "mission" / "state.json"
        save_mission(
            state_path,
            UnboundMission(
                schema_version=1,
                mission_id="acceptance-restore",
                created_at="2026-10-30T00:00:00Z",
                updated_at="2026-10-30T00:00:00Z",
                repo_path=str(repo),
                workspace_path=str(repo),
                branch="main",
                target_branch="main",
                goal="",
                done_when="",
                stage="genesis",
                status="active",
                kernel="grok",
                base_head=head,
                last_milestone_head=head,
            ),
        )
        seen: dict[str, object] = {}

        def kernel(state, prompt, turn_dir, **kwargs):
            workspace = Path(state.workspace_path)
            if "phase" not in seen:
                (workspace / "src" / "seed.py").write_text("VALUE = rejected\n", encoding="utf-8")
                (workspace / "src" / "rejected_extra.py").write_text("rejected\n", encoding="utf-8")
                seen["phase"] = "rejected"
                return KernelTurnResult(
                    kernel=state.kernel,
                    last_message=_decision(
                        "complete",
                        mission_goal="none",
                        done_when="none",
                        done_when_met=True,
                    ),
                    session_id=state.session_id,
                    command=("probe-kernel",),
                    result_path=str(turn_dir / "fake-result.json"),
                )
            seen["seed"] = (workspace / "src" / "seed.py").read_text(encoding="utf-8")
            seen["extra"] = (workspace / "src" / "rejected_extra.py").exists()
            (workspace / "src" / "seed.py").write_text("VALUE = kept\n", encoding="utf-8")
            (workspace / "src" / "kept_extra.py").write_text("kept\n", encoding="utf-8")
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=_decision(
                    "continue",
                    mission_goal=(
                        "Repair the failed sample marker so the operator can read the recovered text."
                    ),
                    done_when="The marker file contains the recovered word.",
                    summary="Recovered the marker after the rejected edit was cleared.",
                ),
                session_id=state.session_id,
                command=("probe-kernel",),
                result_path=str(turn_dir / "fake-result.json"),
            )

        first = run_unbound_turn(state_path, kernel_runner=kernel)
        turn1_seed = (repo / "src" / "seed.py").read_text(encoding="utf-8")
        turn1_extra = (repo / "src" / "rejected_extra.py").exists()
        (repo / "src" / "seed.py").write_text("VALUE = leftover\n", encoding="utf-8")
        (repo / "src" / "rejected_extra.py").write_text("leftover\n", encoding="utf-8")
        second = run_unbound_turn(state_path, kernel_runner=kernel)
        observed = {
            "turn1_accepted": bool((first.get("selection_gate") or {}).get("accepted")),
            "turn1_seed": turn1_seed,
            "turn1_extra": turn1_extra,
            "turn1_clean": bool((first.get("rejected_workspace_restore") or {}).get("clean")),
            "seen_seed": seen.get("seed"),
            "seen_extra": seen.get("extra"),
            "turn2_accepted": bool((second.get("selection_gate") or {}).get("accepted")),
            "turn2_seed": (repo / "src" / "seed.py").read_text(encoding="utf-8"),
            "kept_extra": (repo / "src" / "kept_extra.py").read_text(encoding="utf-8")
            if (repo / "src" / "kept_extra.py").exists()
            else "",
            "other": (repo / "src" / "other.py").read_text(encoding="utf-8"),
            "venv": (venv / "pyvenv.cfg").read_text(encoding="utf-8"),
            "outside": outside.read_text(encoding="utf-8"),
        }
        passed = (
            observed["turn1_accepted"] is False
            and observed["turn1_seed"] == "VALUE = 1\n"
            and observed["turn1_extra"] is False
            and observed["turn1_clean"] is True
            and observed["seen_seed"] == "VALUE = 1\n"
            and observed["seen_extra"] is False
            and observed["turn2_accepted"] is True
            and observed["turn2_seed"] == "VALUE = kept\n"
            and observed["kept_extra"] == "kept\n"
            and observed["other"] == "OTHER = 1\n"
            and observed["venv"] == "keep-venv\n"
            and observed["outside"] == "keep-outside\n"
        )
        return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as error:  # noqa: BLE001 - unmet outcome must still print JSON and exit 0
        passed = False
        observed = {"error": f"{type(error).__name__}: {error}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
