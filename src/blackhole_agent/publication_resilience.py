"""Fail closed when lineage publication is not a fast-forward.

``publish_lineage`` already skips a same-SHA republication and verifies the
remote head after a push. A remote branch that moved to an unrelated commit
still attempted ``git push sha:refs/heads/branch``. Git usually rejected the
non-fast-forward, ``last_publish_error`` stayed sticky, and the continuous
loop retried the same hopeless SHA as ``sleeping_publish_retry`` instead of
creating the next mission.

``publication_failed`` is a catalog class without a closer, so harvest could
never drop it.

This module closes that class:

- refuse a remote head that is not a fast-forward ancestor before push
- keep same-SHA republication idempotent and ancestor fast-forwards live
- drop pending publish on a terminal remote-head mismatch so the loop does
  not stall; keep pending on transient transport errors
- drop the class from genesis fuel once this closer is proved
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
PUBLICATION_FAILED = "publication_failed"
PUBLICATION_RESILIENCE_ID = "capability.publication-resilience"
REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTE_HEAD_MISMATCH_PREFIX = "remote-head mismatch"
TERMINAL_PUBLICATION_MARKERS = (
    REMOTE_HEAD_MISMATCH_PREFIX,
    "not a fast-forward ancestor",
    "non-fast-forward",
)

PUBLICATION_RESILIENCE_DONE_WHEN = (
    f"capability_exists:{PUBLICATION_RESILIENCE_ID};"
    f"capability_proved:{PUBLICATION_RESILIENCE_ID};"
    "no_skill_route"
)
PUBLICATION_RESILIENCE_GOAL = (
    "Repair lineage publication fail-closed on a diverged remote head: an Unbound "
    "publish whose remote branch moved to an unrelated commit still attempts the "
    "fast-forward, so a non-ancestor remote is retried until the continuous loop "
    "stalls. Refuse a remote-head mismatch before push, keep same-SHA republication "
    "idempotent, and structurally close publication_failed."
)


def publication_resilience_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.publication_resilience import "
        "builtin_publication_resilience_proof; r=builtin_publication_resilience_proof(); "
        "assert r['ok'] and r.get('action')=='publication_resilience' "
        "and r.get('passed_count',0) >= 10 "
        "and not r.get('used_skill_route_discovery')\""
    )


def is_remote_head_mismatch(error: str) -> bool:
    """True for the classified diverged-remote refusal."""

    return REMOTE_HEAD_MISMATCH_PREFIX in str(error or "").lower()


def is_terminal_publication_error(error: str) -> bool:
    """True when retrying the same SHA cannot fast-forward the remote."""

    text = str(error or "").lower()
    return any(marker in text for marker in TERMINAL_PUBLICATION_MARKERS)


def apply_publication_failure(loop_state: dict[str, Any], error: str) -> dict[str, Any]:
    """Record a failed publish; a terminal mismatch must not retry forever."""

    payload = loop_state if isinstance(loop_state, dict) else {}
    payload["last_publish_error"] = str(error or "")
    if is_terminal_publication_error(error):
        payload["pending_publish_ref"] = ""
        payload["pending_publish_mission_id"] = ""
    return payload


def harvest_publication_event(loop_state: dict[str, Any]) -> dict[str, str] | None:
    """Shape a sticky continuous-loop publish error as experience fuel."""

    error = str((loop_state or {}).get("last_publish_error") or "").strip()
    if not error:
        return None
    return {
        "class_id": PUBLICATION_FAILED,
        "source": "unbound",
        "summary": "continuous loop publication failed",
        "evidence": error[:400],
    }


def ensure_publication_resilience_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=PUBLICATION_RESILIENCE_ID,
        name="Lineage publication fail-closed on remote-head mismatch",
        description=(
            "Unbound publication refuses a remote branch whose head is not a "
            "fast-forward ancestor before git push, keeps same-SHA republication "
            "idempotent, and drops hopeless pending publishes so the continuous "
            "loop cannot stall on publication_failed. Harvest drops the class "
            "once this closer is proved."
        ),
        kind="python",
        entry="blackhole_agent.publication_resilience:builtin_publication_resilience_proof",
        proof_command=publication_resilience_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        behavior_paths=(
            "src/blackhole_agent/publication_resilience.py",
            "src/blackhole_agent/unbound.py",
            "src/blackhole_agent/kernel_class_closure.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A diverged remote head is refused before push as a classified "
            "remote-head mismatch; same-SHA republication stays idempotent, "
            "the continuous loop does not retry a hopeless SHA, and "
            "publication_failed closes once this closer is proved."
        ),
        tags=("publication", "git", "lineage", "fast-forward", "experience-fuel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260830T042154Z-dbce9e58",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return (completed.stdout or "").strip()


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "pub@test.local")
    _git(repo, "config", "user.name", "Pub Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _bare_remote(root: Path, repo: Path) -> Path:
    remote = root / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "remote", "add", "origin", remote.as_posix())
    _git(repo, "push", "-u", "origin", "main")
    return remote


def _remote_head(remote: Path, branch: str = "main") -> str:
    completed = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "").strip()


def _recording_runner(pushes: list[list[str]]) -> Callable[..., Any]:
    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        tokens = [str(part) for part in command]
        if len(tokens) >= 2 and tokens[0] == "git" and tokens[1] == "push":
            pushes.append(tokens)
        return subprocess.run(command, **kwargs)

    return runner


def _register_proved(root: Path, capability_id: str) -> None:
    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved closer used by publication-resilience proof.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)


def builtin_publication_resilience_proof() -> dict[str, Any]:
    """Hermetic proof: diverged remotes are refused; same-SHA and FF stay live."""

    from blackhole_agent.experience_fuel import harvest_experience
    from blackhole_agent.kernel_class_closure import class_is_closed
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.unbound import publish_lineage, remote_head_is_fast_forward

    checks: dict[str, bool] = {}
    checks["denylists_self"] = PUBLICATION_RESILIENCE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) == (
        PUBLICATION_RESILIENCE_ID,
    )
    checks["detects_classified_mismatch"] = is_remote_head_mismatch(
        f"{REMOTE_HEAD_MISMATCH_PREFIX}: abc is not a fast-forward ancestor of def"
    )
    checks["detects_git_non_fast_forward"] = is_terminal_publication_error(
        "! [rejected] sha -> main (non-fast-forward)"
    )
    checks["ignores_transient_transport"] = not is_terminal_publication_error(
        "simulated remote failure"
    )

    pending = {
        "pending_publish_ref": "abc",
        "pending_publish_mission_id": "m1",
        "last_publish_error": "",
    }
    apply_publication_failure(
        pending,
        f"{REMOTE_HEAD_MISMATCH_PREFIX}: abc is not a fast-forward ancestor of def",
    )
    checks["terminal_mismatch_drops_pending"] = (
        pending["pending_publish_ref"] == ""
        and pending["pending_publish_mission_id"] == ""
        and is_remote_head_mismatch(str(pending["last_publish_error"]))
    )
    transient = {
        "pending_publish_ref": "abc",
        "pending_publish_mission_id": "m1",
        "last_publish_error": "",
    }
    apply_publication_failure(transient, "simulated remote failure")
    checks["transient_error_keeps_pending"] = (
        transient["pending_publish_ref"] == "abc"
        and transient["pending_publish_mission_id"] == "m1"
        and transient["last_publish_error"] == "simulated remote failure"
    )

    with tempfile.TemporaryDirectory(prefix="publication-ff-") as tmp:
        root = Path(tmp)
        repo = _init_repo(root)
        remote = _bare_remote(root, repo)
        seed = _git(repo, "rev-parse", "HEAD")
        (repo / "advance.txt").write_text("next\n", encoding="utf-8")
        _git(repo, "add", "advance.txt")
        _git(repo, "commit", "-m", "advance")
        tip = _git(repo, "rev-parse", "HEAD")
        pushes: list[list[str]] = []
        published = publish_lineage(
            repo,
            tip,
            "origin",
            "main",
            command_runner=_recording_runner(pushes),
        )
        checks["ancestor_fast_forward_publishes"] = (
            published.ok
            and published.remote_before == seed
            and published.remote_after == tip
            and remote_head_is_fast_forward(repo, seed, tip)
            and any(item[:2] == ["git", "push"] for item in pushes)
        )
        idempotent_pushes: list[list[str]] = []
        republished = publish_lineage(
            repo,
            tip,
            "origin",
            "main",
            command_runner=_recording_runner(idempotent_pushes),
        )
        checks["same_sha_republication_is_idempotent"] = (
            republished.ok
            and republished.remote_before == tip
            and republished.remote_after == tip
            and not any(item[:2] == ["git", "push"] for item in idempotent_pushes)
        )
        checks["remote_head_matches_tip"] = _remote_head(remote) == tip

    with tempfile.TemporaryDirectory(prefix="publication-diverge-") as tmp:
        root = Path(tmp)
        repo = _init_repo(root)
        remote = _bare_remote(root, repo)
        seed = _git(repo, "rev-parse", "HEAD")
        (repo / "remote-only.txt").write_text("remote\n", encoding="utf-8")
        _git(repo, "add", "remote-only.txt")
        _git(repo, "commit", "-m", "remote only")
        remote_tip = _git(repo, "rev-parse", "HEAD")
        _git(repo, "push", "origin", "main")
        _git(repo, "reset", "--hard", seed)
        (repo / "local.txt").write_text("local\n", encoding="utf-8")
        _git(repo, "add", "local.txt")
        _git(repo, "commit", "-m", "local advance")
        local_tip = _git(repo, "rev-parse", "HEAD")
        pushes = []
        refused = publish_lineage(
            repo,
            local_tip,
            "origin",
            "main",
            command_runner=_recording_runner(pushes),
        )
        checks["diverged_remote_is_refused"] = (
            refused.ok is False
            and is_remote_head_mismatch(refused.error)
            and refused.remote_before == remote_tip
            and not any(item[:2] == ["git", "push"] for item in pushes)
        )
        checks["diverged_remote_is_unchanged"] = _remote_head(remote) == remote_tip
        checks["unknown_remote_sha_is_not_ancestor"] = (
            remote_head_is_fast_forward(repo, remote_tip, local_tip) is False
            and remote_head_is_fast_forward(repo, "0" * 40, local_tip) is False
        )

    with tempfile.TemporaryDirectory(prefix="publication-new-branch-") as tmp:
        root = Path(tmp)
        repo = _init_repo(root)
        remote = root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            capture_output=True,
            text=True,
        )
        tip = _git(repo, "rev-parse", "HEAD")
        created = publish_lineage(repo, tip, remote.as_posix(), "lineage")
        checks["empty_remote_creates_branch"] = (
            created.ok
            and created.remote_before == ""
            and created.remote_after == tip
        )

    with tempfile.TemporaryDirectory(prefix="publication-harvest-") as tmp:
        root = Path(tmp)
        loop_dir = root / ".blackhole-agent" / "unbound"
        loop_dir.mkdir(parents=True)
        (loop_dir / "continuous-loop.json").write_text(
            json.dumps(
                {
                    "last_publish_error": (
                        f"{REMOTE_HEAD_MISMATCH_PREFIX}: abc is not a "
                        "fast-forward ancestor of def"
                    )
                }
            )
            + "\n",
            encoding="utf-8",
        )
        event = harvest_publication_event(
            json.loads((loop_dir / "continuous-loop.json").read_text(encoding="utf-8"))
        )
        fuel = harvest_experience(root, limit=5)
        checks["harvests_sticky_publish_error"] = (
            event is not None
            and event["class_id"] == PUBLICATION_FAILED
            and any(item.class_id == PUBLICATION_FAILED for item in fuel.candidates)
        )
        _register_proved(root, PUBLICATION_RESILIENCE_ID)
        closed_fuel = harvest_experience(root, limit=5)
        checks["proved_closer_drops_class"] = class_is_closed(
            PUBLICATION_FAILED, root
        ) is True and not any(
            item.class_id == PUBLICATION_FAILED for item in closed_fuel.candidates
        )
        checks["empty_loop_is_not_harvested"] = harvest_publication_event({}) is None

    catalog = DIVERSITY_CATALOG
    checks["catalog_names_publication"] = (
        len(catalog) > 8
        and catalog[8]["id"] == PUBLICATION_RESILIENCE_ID
        and catalog[7]["id"] == "capability.mcp-http-event-stream"
    )
    with tempfile.TemporaryDirectory(prefix="publication-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != PUBLICATION_RESILIENCE_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_publication"] = (
        live_goal == PUBLICATION_RESILIENCE_GOAL
        and PUBLICATION_RESILIENCE_ID in live_done
        and live_source == "genesis_bind_publication"
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_publication_resilience_capability()
    return {
        "ok": ok,
        "action": "publication_resilience",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": PUBLICATION_RESILIENCE_GOAL,
        "done_when": PUBLICATION_RESILIENCE_DONE_WHEN,
    }
