"""Runtime conformance harness: hermetic lifecycle proof for the Unbound controller.

``run_reloadable_tick`` reloads the controller from the mission worktree, so an
agent can rewrite its own runtime between turns. Nothing verified that a
rewritten controller still honors the Unbound contract. This module closes
that gap: it drives a candidate controller module through complete mission
lifecycles in throwaway git repositories with a scripted kernel — no real
kernel process, no network — and asserts the contract at every transition:

- genesis turns adopt mission_goal/done_when into durable state and advance
  the stage to execution without committing anything;
- continue turns persist uncommitted workspace work without a milestone
  commit (durability without paperwork checkpoints);
- milestone turns are committed only when a behavior path changed and every
  reported validation command reproduces under controller replay;
- fabricated validations (exit 0 claimed, real exit non-zero) are rejected;
- paperwork-only milestones (docs/tests/artifacts) are rejected;
- resume reloads state.json from disk and keeps iteration/session continuity;
- complete requires done_when_met and passes machine-checkable contracts.

The suite runs against any candidate controller module (the installed
``blackhole_agent.unbound`` by default, or a rewritten ``unbound.py`` loaded
from a file path), which is what makes self-modification gateable: a candidate
controller that breaks any scenario fails the suite before it can govern a
real mission. ``builtin_runtime_conformance`` is the invocable entry point;
its report digest is a pure function of scenario names and verdicts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("artifacts") / "runtime-conformance"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def default_report_dir(repo_path: Path) -> Path:
    return repo_path / DEFAULT_REPORT_DIR


def load_controller(path: Path | None = None) -> ModuleType:
    """Load a candidate controller module (default: installed unbound)."""

    if path is None:
        from blackhole_agent import unbound

        return unbound
    path = path.resolve()
    spec = importlib.util.spec_from_file_location("blackhole_agent.candidate_unbound", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load candidate controller: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve cls.__module__ here
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_operator_repo(repo: Path) -> None:
    """Create a minimal operator repository with one real behavior path."""

    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Conformance Harness")
    _git(repo, "config", "user.email", "conformance@example.invalid")
    (repo / "src").mkdir()
    (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# operator repo\n", encoding="utf-8")
    # Hermeticity guard: the milestone gate's goal watchdog shells out with
    # cwd=workspace; an empty shadow package makes the capability_watchdog
    # import fail there, so the gate takes its designed "pre-watchdog
    # worktree" skip path instead of evaluating the ambient repository's
    # goals inside a minimal operator repo (environment-dependent verdicts).
    (repo / "blackhole_agent").mkdir()
    (repo / "blackhole_agent" / "__init__.py").write_text(
        '"""Shadow package: minimal operator repos predate the goal watchdog."""\n',
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")


def _decision(status: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "mission_goal": "",
        "done_when": "",
        "summary": "Exercised one lifecycle transition.",
        "strategy": "Drive the controller contract directly.",
        "next_step": "Run the next lifecycle scenario.",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "done_when_met": False,
        "commit_message": "",
    }
    payload.update(overrides)
    return payload


class ScriptedKernel:
    """Kernel-runner stand-in: returns scripted decisions in order."""

    def __init__(self, decisions: Iterable[dict[str, Any]]):
        self._decisions = list(decisions)
        self.prompts: list[str] = []

    def __call__(self, state: Any, prompt: str, turn_dir: Path, command_runner: Any = None) -> Any:
        from blackhole_agent.unbound import KernelTurnResult

        if not self._decisions:
            raise RuntimeError("scripted kernel ran out of decisions")
        self.prompts.append(prompt)
        decision = self._decisions.pop(0)
        turn_dir.mkdir(parents=True, exist_ok=True)
        return KernelTurnResult(
            kernel="scripted",
            last_message=json.dumps(decision),
            session_id="scripted-session-1",
            command=("scripted-kernel",),
            result_path="",
        )


def _scripted_kernel_resolver(kernel: str) -> tuple[str, dict[str, Any]]:
    return kernel, {"requested": kernel, "resolved": kernel, "source": "scripted"}


def _create_mission(
    controller: ModuleType,
    repo: Path,
    scratch: Path,
    *,
    goal: str = "",
    done_when: str = "",
) -> Path:
    return controller.create_mission(
        repo_path=repo,
        goal=goal,
        done_when=done_when,
        kernel="scripted",
        worktree_parent=scratch / "worktrees",
        kernel_resolver=_scripted_kernel_resolver,
    )


def _events(mission_dir: Path) -> list[dict[str, Any]]:
    path = mission_dir / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _behavior_change(workspace: Path, value: int) -> None:
    (workspace / "src" / "seed.py").write_text(f"VALUE = {value}\n", encoding="utf-8")


def _check(results: list[dict[str, Any]], name: str, ok: bool, detail: str = "") -> None:
    results.append({"name": name, "ok": bool(ok), "detail": detail})


def _scenario_result(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def scenario_genesis_adopts_mission(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """A genesis turn writes goal/done_when into durable state, commits nothing."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    base_head = _git(repo, "rev-parse", "HEAD")
    state_path = _create_mission(controller, repo, scratch)
    state = controller.load_mission(state_path)
    _check(checks, "genesis stage recorded", state.stage == "genesis", state.stage)

    kernel = ScriptedKernel(
        [
            _decision(
                "continue",
                mission_goal="Prove the controller contract hermetically.",
                done_when="Every lifecycle scenario passes against the candidate controller.",
            )
        ]
    )
    record = controller.run_unbound_turn(state_path, kernel_runner=kernel)
    state = controller.load_mission(state_path)
    _check(checks, "goal adopted", state.goal == "Prove the controller contract hermetically.", state.goal)
    _check(checks, "done_when adopted", state.done_when.startswith("Every lifecycle scenario"), state.done_when)
    _check(checks, "stage advanced to execution", state.stage == "execution", state.stage)
    _check(checks, "no commit on genesis turn", _git(Path(state.workspace_path), "rev-parse", "HEAD") == base_head)
    _check(checks, "turn record persisted", (state_path.parent / "turns" / "0001" / "turn.json").exists())
    kinds = {event.get("event") for event in _events(state_path.parent)}
    _check(checks, "mission.created event recorded", "mission.created" in kinds, ",".join(sorted(kinds)))
    _check(checks, "turn.completed event recorded", "turn.completed" in kinds, ",".join(sorted(kinds)))
    _check(checks, "record reports iteration 1", record.get("iteration") == 1, str(record.get("iteration")))
    return _scenario_result("genesis_adopts_mission", checks)


def scenario_continue_preserves_work(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """Continue turns keep uncommitted workspace work and commit nothing."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    base_head = _git(repo, "rev-parse", "HEAD")
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    _behavior_change(workspace, 2)

    record = controller.run_unbound_turn(state_path, kernel_runner=ScriptedKernel([_decision("continue")]))
    _check(checks, "effective status continue", record.get("effective_status") == "continue")
    _check(checks, "no commit on continue", _git(workspace, "rev-parse", "HEAD") == base_head)
    dirty = _git(workspace, "status", "--porcelain")
    _check(checks, "uncommitted work survives the turn", "src/seed.py" in dirty, dirty or "(clean)")
    state = controller.load_mission(state_path)
    _check(checks, "mission stays active", state.status == "active", state.status)
    _check(checks, "no milestone recorded", state.milestone_count == 0, str(state.milestone_count))
    return _scenario_result("continue_preserves_work", checks)


def scenario_milestone_commits_reproducible(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """A milestone with a behavior change and reproducible validation is committed."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    base_head = _git(repo, "rev-parse", "HEAD")
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    _behavior_change(workspace, 3)

    record = controller.run_unbound_turn(
        state_path,
        kernel_runner=ScriptedKernel(
            [
                _decision(
                    "milestone",
                    capability_delta="Seed value advanced through the gated path.",
                    outcome_evidence=["src/seed.py updated in workspace"],
                    validation=[{"command": "git rev-parse --verify HEAD", "exit_code": 0, "summary": "head resolves"}],
                    commit_message="feat: advance seed capability",
                )
            ]
        ),
    )
    _check(checks, "milestone accepted", record.get("milestone_gate", {}).get("accepted") is True,
           "; ".join(record.get("milestone_gate", {}).get("reasons") or []))
    _check(checks, "commit recorded", bool(record.get("commit_sha")), str(record.get("commit_sha")))
    head = _git(workspace, "rev-parse", "HEAD")
    _check(checks, "workspace head advanced", head != base_head, head)
    state = controller.load_mission(state_path)
    _check(checks, "milestone count incremented", state.milestone_count == 1, str(state.milestone_count))
    _check(checks, "last milestone head updated", state.last_milestone_head == head, state.last_milestone_head)
    kinds = {event.get("event") for event in _events(state_path.parent)}
    _check(checks, "milestone event recorded", "mission.milestone" in kinds, ",".join(sorted(kinds)))
    return _scenario_result("milestone_commits_reproducible", checks)


def scenario_fabricated_validation_rejected(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """A validation claim that does not reproduce under replay is refused."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    base_head = _git(repo, "rev-parse", "HEAD")
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    _behavior_change(workspace, 4)

    record = controller.run_unbound_turn(
        state_path,
        kernel_runner=ScriptedKernel(
            [
                _decision(
                    "milestone",
                    capability_delta="Fabricated claim attempt.",
                    outcome_evidence=["claimed but not reproducible"],
                    validation=[
                        {
                            "command": "git rev-parse --verify refs/heads/does-not-exist",
                            "exit_code": 0,
                            "summary": "fabricated success",
                        }
                    ],
                )
            ]
        ),
    )
    gate = record.get("milestone_gate", {})
    _check(checks, "gate rejected the fabrication", gate.get("accepted") is False)
    reasons = "; ".join(gate.get("reasons") or [])
    _check(checks, "replay failure reported", "validation replay failed" in reasons or "reproduced" in reasons, reasons)
    _check(checks, "status downgraded to continue", record.get("effective_status") == "continue")
    _check(checks, "no commit recorded", not record.get("commit_sha"), str(record.get("commit_sha")))
    _check(checks, "workspace head unchanged", _git(workspace, "rev-parse", "HEAD") == base_head)
    state = controller.load_mission(state_path)
    _check(checks, "no milestone counted", state.milestone_count == 0, str(state.milestone_count))
    return _scenario_result("fabricated_validation_rejected", checks)


def scenario_paperwork_milestone_rejected(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """Docs/tests/artifacts-only changes cannot earn a milestone."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    base_head = _git(repo, "rev-parse", "HEAD")
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    (workspace / "README.md").write_text("# operator repo\n\nmore docs\n", encoding="utf-8")

    record = controller.run_unbound_turn(
        state_path,
        kernel_runner=ScriptedKernel(
            [
                _decision(
                    "milestone",
                    capability_delta="Docs-only attempt.",
                    outcome_evidence=["README updated"],
                    validation=[{"command": "git rev-parse --verify HEAD", "exit_code": 0, "summary": "head resolves"}],
                )
            ]
        ),
    )
    gate = record.get("milestone_gate", {})
    _check(checks, "paperwork gate rejected", gate.get("accepted") is False)
    reasons = "; ".join(gate.get("reasons") or [])
    _check(checks, "docs-only reason reported", "docs, tests, artifacts" in reasons, reasons)
    _check(checks, "no commit recorded", not record.get("commit_sha"), str(record.get("commit_sha")))
    _check(checks, "workspace head unchanged", _git(workspace, "rev-parse", "HEAD") == base_head)
    return _scenario_result("paperwork_milestone_rejected", checks)


def scenario_resume_keeps_continuity(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """Reloading state.json between turns preserves iteration and session."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    controller.run_unbound_turn(state_path, kernel_runner=ScriptedKernel([_decision("continue")]))
    reloaded = controller.load_mission(state_path)
    _check(checks, "iteration persisted across reload", reloaded.iteration == 1, str(reloaded.iteration))
    _check(checks, "session id persisted across reload", reloaded.session_id == "scripted-session-1", reloaded.session_id)
    _check(checks, "recent turns persisted", len(reloaded.recent_turns) == 1, str(len(reloaded.recent_turns)))

    second = controller.run_unbound_turn(state_path, kernel_runner=ScriptedKernel([_decision("continue")]))
    _check(checks, "second turn increments iteration", second.get("iteration") == 2, str(second.get("iteration")))
    _check(checks, "session continuity kept", second.get("session_id") == "scripted-session-1",
           str(second.get("session_id")))
    state = controller.load_mission(state_path)
    _check(checks, "history bounded and ordered", [t.get("iteration") for t in state.recent_turns] == [1, 2])
    return _scenario_result("resume_keeps_continuity", checks)


def scenario_complete_requires_contract(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """Complete is refused on unmet contracts and accepted when honestly met."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="min_capabilities:999999",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    _behavior_change(workspace, 5)

    rejected = controller.run_unbound_turn(
        state_path,
        kernel_runner=ScriptedKernel(
            [
                _decision(
                    "complete",
                    capability_delta="Premature completion attempt.",
                    outcome_evidence=["behavior changed"],
                    validation=[{"command": "git rev-parse --verify HEAD", "exit_code": 0, "summary": "head resolves"}],
                    done_when_met=True,
                    done_when="min_capabilities:999999",
                )
            ]
        ),
    )
    gate = rejected.get("milestone_gate", {})
    _check(checks, "premature complete rejected", gate.get("accepted") is False)
    reasons = "; ".join(gate.get("reasons") or [])
    _check(checks, "machine-checkable failure reported", "machine-checkable done_when failed" in reasons, reasons)
    state = controller.load_mission(state_path)
    _check(checks, "mission stays active after rejection", state.status == "active", state.status)

    repo2 = scratch / "repo-honest"
    _init_operator_repo(repo2)
    state_path2 = _create_mission(
        controller,
        repo2,
        scratch / "worktrees-honest",
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state2 = controller.load_mission(state_path2)
    workspace2 = Path(state2.workspace_path)
    _behavior_change(workspace2, 6)
    accepted = controller.run_unbound_turn(
        state_path2,
        kernel_runner=ScriptedKernel(
            [
                _decision(
                    "complete",
                    capability_delta="Honest completion path.",
                    outcome_evidence=["behavior changed"],
                    validation=[{"command": "git rev-parse --verify HEAD", "exit_code": 0, "summary": "head resolves"}],
                    done_when_met=True,
                    done_when="",
                )
            ]
        ),
    )
    _check(checks, "honest complete accepted", accepted.get("milestone_gate", {}).get("accepted") is True,
           "; ".join(accepted.get("milestone_gate", {}).get("reasons") or []))
    _check(checks, "complete status effective", accepted.get("effective_status") == "complete")
    state2 = controller.load_mission(state_path2)
    _check(checks, "mission recorded complete", state2.status == "complete", state2.status)
    return _scenario_result("complete_requires_contract", checks)


SCENARIOS: tuple[tuple[str, Callable[[ModuleType, Path], dict[str, Any]]], ...] = (
    ("genesis_adopts_mission", scenario_genesis_adopts_mission),
    ("continue_preserves_work", scenario_continue_preserves_work),
    ("milestone_commits_reproducible", scenario_milestone_commits_reproducible),
    ("fabricated_validation_rejected", scenario_fabricated_validation_rejected),
    ("paperwork_milestone_rejected", scenario_paperwork_milestone_rejected),
    ("resume_keeps_continuity", scenario_resume_keeps_continuity),
    ("complete_requires_contract", scenario_complete_requires_contract),
)


def run_conformance_suite(
    controller: ModuleType | None = None,
    *,
    only: Iterable[str] | None = None,
    scratch_root: Path | None = None,
) -> dict[str, Any]:
    """Run lifecycle scenarios against a candidate controller module."""

    if controller is None:
        controller = load_controller()
    wanted = set(only) if only is not None else None
    results: list[dict[str, Any]] = []

    def run_all(scratch_base: Path) -> None:
        for name, scenario in SCENARIOS:
            if wanted is not None and name not in wanted:
                continue
            scenario_scratch = scratch_base / name
            scenario_scratch.mkdir(parents=True, exist_ok=True)
            try:
                results.append(scenario(controller, scenario_scratch))
            except Exception as error:  # a crashing controller fails the scenario
                results.append(
                    {
                        "name": name,
                        "ok": False,
                        "checks": [
                            {
                                "name": "scenario_completed",
                                "ok": False,
                                "detail": f"{type(error).__name__}: {error}",
                            }
                        ],
                    }
                )

    if scratch_root is not None:
        scratch_root.mkdir(parents=True, exist_ok=True)
        run_all(scratch_root)
    else:
        with tempfile.TemporaryDirectory(prefix="blackhole-conformance-") as tmp:
            run_all(Path(tmp))

    verdicts = [{"name": item["name"], "ok": item["ok"]} for item in results]
    digest = hashlib.sha256(
        json.dumps(verdicts, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "ok": bool(results) and all(item["ok"] for item in results),
        "action": "runtime_conformance_suite",
        "schema_version": SCHEMA_VERSION,
        "controller": getattr(controller, "__file__", "") or "",
        "scenario_count": len(results),
        "scenarios": results,
        "verdict_digest": digest,
    }


def builtin_runtime_conformance() -> dict[str, Any]:
    """Invocable capability entry: suite against the installed controller."""

    repo_path = Path(__file__).resolve().parents[2]
    report = run_conformance_suite()
    report["reported_at"] = utc_now_iso()
    report_path = default_report_dir(repo_path) / "conformance-report.json"
    atomic_write_json(report_path, report)
    report["report_path"] = str(report_path)
    return report
