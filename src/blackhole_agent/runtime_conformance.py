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
- complete requires done_when_met and passes machine-checkable contracts;
- the reload boundary is real: ``run_reloadable_tick`` runs the tick in a
  fresh interpreter governed by the *worktree's* controller copy — a patched
  copy governs the tick, a corrupted copy fails it;
- publication fast-forwards the proven commit to the remote branch and
  verifies the remote head, idempotently, and refuses missing commits.

The suite runs against any candidate controller module (the installed
``blackhole_agent.unbound`` by default, or a rewritten ``unbound.py`` loaded
from a file path), which is what makes self-modification gateable: a candidate
controller that breaks any scenario fails the suite before it can govern a
real mission. ``run_mutation_gate`` proves the suite's honesty: it seeds
distinct contract violations (permissive gate, replay-blind gate, broken
decision parser, non-durable state, paperwork-blind classification,
contract-blind completion, reload short-circuit) and passes only when the
suite catches every one. ``builtin_runtime_conformance`` is the invocable
entry point; its report digest is a pure function of scenario and mutation
verdicts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
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


def _init_operator_repo(repo: Path, *, shadow: bool = True) -> None:
    """Create a minimal operator repository with one real behavior path."""

    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Conformance Harness")
    _git(repo, "config", "user.email", "conformance@example.invalid")
    (repo / "src").mkdir()
    (repo / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# operator repo\n", encoding="utf-8")
    if shadow:
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


def _copy_runtime_package(controller: ModuleType, repo: Path) -> None:
    """Commit a full copy of the candidate controller's package into the repo."""

    package_dir = Path(controller.__file__).resolve().parent
    destination = repo / "src" / package_dir.name
    shutil.copytree(
        package_dir,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "runtime package")


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


def scenario_status_paths_reported_exactly(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """Porcelain status paths are reported exactly, including the first line.

    ``git status --porcelain=v1`` prefixes entries with a two-column status
    and one space; stripping the whole command output mangles the first
    entry's path (``src/seed.py`` -> ``rc/seed.py``), which both corrupts
    durable records and can misclassify gated paths (a mangled
    ``capabilities/ledger.json`` stops matching the non-behavior prefix).
    Dotfile paths must keep their leading dot as well.
    """

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    (repo / "capabilities").mkdir()
    (repo / "capabilities" / "ledger.json").write_text("{}\n", encoding="utf-8")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "gated surfaces")
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)

    (workspace / "src" / "seed.py").write_text("VALUE = 7\n", encoding="utf-8")
    (workspace / "capabilities" / "ledger.json").write_text('{"changed": true}\n', encoding="utf-8")
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci2\n", encoding="utf-8")

    paths = controller.status_changed_paths(workspace)
    _check(checks, "seed path exact", "src/seed.py" in paths, ",".join(paths))
    _check(checks, "ledger path exact", "capabilities/ledger.json" in paths, ",".join(paths))
    _check(checks, "dotfile path keeps leading dot", ".github/workflows/ci.yml" in paths, ",".join(paths))
    missing = [path for path in paths if not (workspace / path).exists()]
    _check(checks, "every reported path names a real file", not missing, ",".join(missing))
    behavior = sorted(path for path in paths if controller.is_behavior_path(path))
    _check(
        checks,
        "behavior classification intact",
        behavior == [".github/workflows/ci.yml", "capabilities/ledger.json", "src/seed.py"],
        ",".join(behavior),
    )
    return _scenario_result("status_paths_reported_exactly", checks)


_INVOKE_KERNEL_SPAN = re.compile(r"^def invoke_kernel_turn\(.*?(?=^def )", re.DOTALL | re.MULTILINE)

_SCRIPTED_INVOKE_TEMPLATE = '''def invoke_kernel_turn(
    state,
    prompt,
    turn_dir,
    *,
    command_runner=None,
):
    """Conformance patch: scripted kernel proving worktree-controller governance."""

    return KernelTurnResult(
        kernel="scripted-reload",
        last_message={decision!r},
        session_id="reload-session",
        command=("worktree-controller",),
        result_path="",
    )


'''


def scenario_reload_boundary_governs_tick(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """run_reloadable_tick runs the tick under the worktree's controller copy.

    The operator repo carries a full copy of the candidate package, so the
    mission worktree contains ``src/blackhole_agent/unbound.py``. Patching
    that copy (a scripted kernel) must govern the next tick; corrupting it
    must fail the tick. Both directions prove the reload boundary loads the
    evolving worktree code rather than the invoking checkout's code.
    """

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo, shadow=False)
    _copy_runtime_package(controller, repo)
    state_path = _create_mission(
        controller,
        repo,
        scratch,
        goal="Grow a capability.",
        done_when="The capability is invocable.",
    )
    state = controller.load_mission(state_path)
    workspace = Path(state.workspace_path)
    worktree_runtime = workspace / "src" / "blackhole_agent" / "unbound.py"
    _check(checks, "worktree carries controller copy", worktree_runtime.exists())

    source = worktree_runtime.read_text(encoding="utf-8")
    decision = json.dumps(_decision("continue", summary="governed-by-worktree-controller"))
    patched, count = _INVOKE_KERNEL_SPAN.subn(_SCRIPTED_INVOKE_TEMPLATE.format(decision=decision), source)
    _check(checks, "invoke_kernel_turn patch applied once", count == 1, f"replacements={count}")
    worktree_runtime.write_text(patched, encoding="utf-8")

    returncode = controller.run_reloadable_tick(state_path)
    _check(checks, "reloadable tick succeeded", returncode == 0, f"returncode={returncode}")
    turn_record_path = state_path.parent / "turns" / "0001" / "turn.json"
    if turn_record_path.exists():
        turn_record = json.loads(turn_record_path.read_text(encoding="utf-8"))
    else:
        turn_record = {}
    _check(checks, "turn governed by worktree controller", turn_record.get("kernel") == "scripted-reload",
           str(turn_record.get("kernel")))
    _check(checks, "worktree command recorded", turn_record.get("command") == ["worktree-controller"],
           str(turn_record.get("command")))
    final_message_path = state_path.parent / "turns" / "0001" / "final-message.md"
    final_message = final_message_path.read_text(encoding="utf-8") if final_message_path.exists() else ""
    _check(checks, "scripted decision delivered", "governed-by-worktree-controller" in final_message)
    state = controller.load_mission(state_path)
    _check(checks, "iteration persisted through reload", state.iteration == 1, str(state.iteration))
    _check(checks, "session persisted through reload", state.session_id == "reload-session", state.session_id)

    worktree_runtime.write_text(patched + "\ndef broken(:\n", encoding="utf-8")
    broken_returncode = controller.run_reloadable_tick(state_path)
    _check(checks, "corrupted worktree controller fails the tick", broken_returncode != 0,
           f"returncode={broken_returncode}")
    return _scenario_result("reload_boundary_governs_tick", checks)


def scenario_publication_verifies_remote(controller: ModuleType, scratch: Path) -> dict[str, Any]:
    """publish_lineage fast-forwards a real remote and verifies its head."""

    checks: list[dict[str, Any]] = []
    repo = scratch / "repo"
    _init_operator_repo(repo)
    remote = scratch / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "remote", "add", "origin", remote.as_posix())
    _git(repo, "push", "-u", "origin", "main")

    (repo / "src" / "seed.py").write_text("VALUE = 10\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "advance seed")
    sha = _git(repo, "rev-parse", "HEAD")

    published = controller.publish_lineage(repo, sha, "origin", "lineage")
    _check(checks, "publication ok", published.ok, published.error)
    _check(checks, "remote head verified after push", published.remote_after == sha, published.remote_after)
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/lineage"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _check(checks, "bare remote carries lineage branch", remote_head == sha, remote_head)

    republished = controller.publish_lineage(repo, sha, "origin", "lineage")
    _check(checks, "republication idempotent", republished.ok and republished.remote_before == sha,
           f"before={republished.remote_before} error={republished.error}")

    missing = controller.publish_lineage(repo, "0" * 40, "origin", "lineage")
    _check(checks, "missing commit refused", not missing.ok and "does not exist" in missing.error, missing.error)
    return _scenario_result("publication_verifies_remote", checks)


SCENARIOS: tuple[tuple[str, Callable[[ModuleType, Path], dict[str, Any]]], ...] = (
    ("genesis_adopts_mission", scenario_genesis_adopts_mission),
    ("continue_preserves_work", scenario_continue_preserves_work),
    ("milestone_commits_reproducible", scenario_milestone_commits_reproducible),
    ("fabricated_validation_rejected", scenario_fabricated_validation_rejected),
    ("paperwork_milestone_rejected", scenario_paperwork_milestone_rejected),
    ("resume_keeps_continuity", scenario_resume_keeps_continuity),
    ("complete_requires_contract", scenario_complete_requires_contract),
    ("status_paths_reported_exactly", scenario_status_paths_reported_exactly),
    ("reload_boundary_governs_tick", scenario_reload_boundary_governs_tick),
    ("publication_verifies_remote", scenario_publication_verifies_remote),
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


def _patch_attr(controller: ModuleType, name: str, value: Any) -> Callable[[], None]:
    original = getattr(controller, name)

    def restore() -> None:
        setattr(controller, name, original)

    setattr(controller, name, value)
    return restore


def _mutation_permissive_gate(controller: ModuleType) -> Callable[[], None]:
    def permissive(
        decision: Any,
        *,
        changed_paths: list[str],
        workspace: Path | None = None,
        mission_done_when: str = "",
    ) -> Any:
        return controller.MilestoneGate(
            requested=decision.status in {"milestone", "complete"},
            accepted=True,
            reasons=(),
            changed_paths=tuple(changed_paths),
            behavior_paths=tuple(changed_paths),
        )

    return _patch_attr(controller, "evaluate_milestone", permissive)


def _mutation_replay_blind(controller: ModuleType) -> Callable[[], None]:
    def blind_replay(
        workspace: Path,
        command: str,
        *,
        timeout: int = 300,
        command_runner: Any = None,
    ) -> dict[str, Any]:
        return {
            "command": command,
            "reported_exit_code": 0,
            "reproduced_exit_code": 0,
            "timed_out": False,
            "ok": True,
        }

    return _patch_attr(controller, "replay_validation_command", blind_replay)


def _mutation_decision_parser(controller: ModuleType) -> Callable[[], None]:
    return _patch_attr(controller, "extract_json_decision", lambda message: {})


def _mutation_non_durable_state(controller: ModuleType) -> Callable[[], None]:
    return _patch_attr(controller, "save_mission", lambda state_path, state: None)


def _mutation_paperwork_blind(controller: ModuleType) -> Callable[[], None]:
    return _patch_attr(controller, "is_behavior_path", lambda path: True)


def _mutation_contract_blind(controller: ModuleType) -> Callable[[], None]:
    from blackhole_agent.capability_compounder import parse_outcome_contract

    class ContractBlindCompounder:
        @staticmethod
        def parse_outcome_contract(done_when: str) -> dict[str, Any]:
            return parse_outcome_contract(done_when)

        @staticmethod
        def evaluate_outcome_contract(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"met": True, "failed": []}

    return _patch_attr(controller, "reload_worktree_compounder", lambda: ContractBlindCompounder)


def _mutation_reload_shortcircuit(controller: ModuleType) -> Callable[[], None]:
    def in_process_tick(state_path: Path) -> int:
        controller.run_unbound_turn(state_path)
        return 0

    return _patch_attr(controller, "run_reloadable_tick", in_process_tick)


MUTATIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "permissive_gate",
        "violates": "milestone gate accepts every claim without evidence",
        "apply": _mutation_permissive_gate,
        "scenarios": (
            "fabricated_validation_rejected",
            "paperwork_milestone_rejected",
            "complete_requires_contract",
        ),
    },
    {
        "name": "replay_blind_gate",
        "violates": "validation replay trusts reported exit codes",
        "apply": _mutation_replay_blind,
        "scenarios": ("fabricated_validation_rejected",),
    },
    {
        "name": "broken_decision_parser",
        "violates": "agent decision JSON is discarded",
        "apply": _mutation_decision_parser,
        "scenarios": ("genesis_adopts_mission",),
    },
    {
        "name": "non_durable_state",
        "violates": "mission state is never persisted",
        "apply": _mutation_non_durable_state,
        "scenarios": ("resume_keeps_continuity",),
    },
    {
        "name": "paperwork_blind_gate",
        "violates": "docs-only changes count as behavior",
        "apply": _mutation_paperwork_blind,
        "scenarios": ("paperwork_milestone_rejected",),
    },
    {
        "name": "contract_blind_gate",
        "violates": "machine-checkable done_when always reports met",
        "apply": _mutation_contract_blind,
        "scenarios": ("complete_requires_contract",),
    },
    {
        "name": "reload_shortcircuit",
        "violates": "tick runs the invoking checkout instead of the worktree controller",
        "apply": _mutation_reload_shortcircuit,
        "scenarios": ("reload_boundary_governs_tick",),
    },
)


def run_mutation_gate(
    controller: ModuleType | None = None,
    *,
    mutations: Iterable[dict[str, Any]] = MUTATIONS,
) -> dict[str, Any]:
    """Prove the conformance suite catches seeded controller violations.

    Each mutation injects one distinct contract violation into the candidate
    controller; the gate passes only when the suite rejects every one of
    them (the targeted scenarios fail) and the controller is restored
    afterwards. A suite that cannot catch these mutations cannot gate
    self-modification.
    """

    if controller is None:
        controller = load_controller()
    results: list[dict[str, Any]] = []
    for mutation in mutations:
        restore = mutation["apply"](controller)
        try:
            report = run_conformance_suite(controller, only=mutation["scenarios"])
        finally:
            restore()
        failed = sorted(s["name"] for s in report["scenarios"] if not s["ok"])
        expected = sorted(mutation["scenarios"])
        caught = not report["ok"] and all(name in failed for name in expected)
        results.append(
            {
                "name": mutation["name"],
                "violates": mutation["violates"],
                "expected_failures": expected,
                "observed_failures": failed,
                "caught": caught,
            }
        )
    verdicts = [{"name": item["name"], "caught": item["caught"]} for item in results]
    digest = hashlib.sha256(json.dumps(verdicts, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "ok": bool(results) and all(item["caught"] for item in results),
        "action": "runtime_mutation_gate",
        "schema_version": SCHEMA_VERSION,
        "controller": getattr(controller, "__file__", "") or "",
        "mutation_count": len(results),
        "mutations": results,
        "verdict_digest": digest,
    }


def builtin_runtime_conformance() -> dict[str, Any]:
    """Invocable capability entry: suite plus mutation gate, digest-sealed."""

    repo_path = Path(__file__).resolve().parents[2]
    controller = load_controller()
    suite = run_conformance_suite(controller)
    gate = run_mutation_gate(controller) if suite["ok"] else {
        "ok": False,
        "action": "runtime_mutation_gate",
        "mutations": [],
        "mutation_count": 0,
        "verdict_digest": "",
        "skipped": "conformance suite not green",
    }
    report = {
        "ok": bool(suite["ok"]) and bool(gate["ok"]),
        "action": "runtime_conformance_proof",
        "schema_version": SCHEMA_VERSION,
        "reported_at": utc_now_iso(),
        "suite": suite,
        "mutation_gate": gate,
        "verdict_digest": hashlib.sha256(
            json.dumps(
                {"suite": suite["verdict_digest"], "gate": gate["verdict_digest"]},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    report_path = default_report_dir(repo_path) / "conformance-report.json"
    atomic_write_json(report_path, report)
    report["report_path"] = str(report_path)
    return report
