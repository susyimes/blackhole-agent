"""Inspect receiving Git histories and recover publishable lineage commits.

In August 2026 the loop retried a protected-path refusal 222 times. In
November it discarded a clean sibling of a newly published soul.md edit.
Local ancestry and protected-path review determine which changes can land.
An unreadable receiver leaves the publication pending for a later attempt.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from blackhole_agent.capability_compounder import (
    Capability,
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
RECEIVER_FETCH_ERROR = "Unable to fetch receiver commit"
# Harvested 2026-08-17..2026-08-22. The same SHA was retried 222 times.
# The gate still refuses the push; only the hopeless pending retry is dropped.
PROTECTED_PATH_REFUSAL_MARKER = "protected paths require operator acknowledgment"
TERMINAL_PUBLICATION_MARKERS = (
    REMOTE_HEAD_MISMATCH_PREFIX,
    "not a fast-forward ancestor",
    "non-fast-forward",
    PROTECTED_PATH_REFUSAL_MARKER,
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
    """True when retrying the same SHA cannot publish.

    A diverged remote and a protected-path acknowledgment refusal are terminal.
    DNS, connect, empty-reply, schannel, and http.postBuffer failures are not:
    those can succeed on a later attempt.
    """

    text = str(error or "").lower()
    if text.startswith(RECEIVER_FETCH_ERROR.lower()):
        return False  # A transport diagnostic cannot establish divergent ancestry.
    return any(marker in text for marker in TERMINAL_PUBLICATION_MARKERS)


# Harvested 2026-08-23 continuous-loop publication. Git asked for a larger
# HTTP buffer after curl 65 and a sideband disconnect. A schannel handshake
# failure does not contain this phrase and is retried as its own class.
POST_BUFFER_OVERFLOW_MARKER = "http.postbuffer"
POST_BUFFER_RETRY_BYTES = 524288000
# Harvested continuous-loop publications from 2026-07-29 through 2026-10-29.
# Git died in Windows schannel before or during the push, and the error did
# not ask for a larger buffer. The postBuffer rewind text also mentions
# "server closed abruptly"; that class keeps the enlarged-buffer retry.
_SCHANNEL_HANDSHAKE_MARKERS = (
    "failed to receive handshake",
    "server closed abruptly",
    "missing close_notify",
)


def is_post_buffer_overflow(error: str) -> bool:
    """True when git itself asked the push to increase http.postBuffer."""

    return POST_BUFFER_OVERFLOW_MARKER in str(error or "").lower()


def is_schannel_handshake_failure(error: str) -> bool:
    """True for a harvested schannel TLS abort that did not ask for a larger buffer."""

    text = str(error or "").lower()
    if POST_BUFFER_OVERFLOW_MARKER in text or "schannel:" not in text:
        return False
    return any(marker in text for marker in _SCHANNEL_HANDSHAKE_MARKERS)


# Harvested continuous-loop publications. 2026-10-15 died with curl's empty
# reply. 2026-08-11 died with a connect timeout and with DNS failure. None of
# those asked for a larger buffer or named schannel. Each is retried once.
_HTTP_TRANSPORT_ABORT_MARKERS = (
    "empty reply from server",
    "could not connect to",
    "could not resolve host",
)


def is_http_transport_abort(error: str) -> bool:
    """True for a harvested GitHub HTTP abort that is not schannel or postBuffer.

    Empty reply, connect failure, and DNS failure share one retry. A schannel
    handshake and an http.postBuffer request keep their own paths.
    """

    text = str(error or "").lower()
    if POST_BUFFER_OVERFLOW_MARKER in text or "schannel:" in text:
        return False
    return any(marker in text for marker in _HTTP_TRANSPORT_ABORT_MARKERS)


def publication_read_targets(repo: Path, remote: str, command_runner: Callable[..., Any]) -> tuple[str | None, ...]:
    """None reads through the original remote. Other entries are resolved push URLs."""
    from blackhole_agent.unbound import run_command

    def config(*args: str) -> subprocess.CompletedProcess:
        return run_command(["git", *args], cwd=repo, command_runner=command_runner, check=False)

    push = config("remote", "get-url", "--push", "--all", "--", remote)
    if push.returncode == 2:  # A literal repository argument, outside the named remotes.
        rules = config("config", "--null", "--get-regexp", r"^url\..*\.pushinsteadof$")
        if rules.returncode not in (0, 1):
            raise RuntimeError(rules.stderr.strip() or "Unable to read Git push URL rewrites")
        matches = []
        for rule in rules.stdout.split("\0"):
            key, sep, prefix = rule.partition("\n")
            if sep and remote.startswith(prefix):
                matches.append((prefix, key[4:-len(".pushinsteadof")]))
        if not matches:
            return (None,)
        prefix, base = max(matches, key=lambda pair: len(pair[0]))
        return (base + remote[len(prefix):],)
    if push.returncode or not push.stdout.splitlines():
        raise RuntimeError(push.stderr.strip() or "Unable to resolve Git push destinations")
    fetch = config("remote", "get-url", "--", remote)
    if fetch.returncode:
        raise RuntimeError(fetch.stderr.strip() or "Unable to resolve Git fetch URL")
    # Keep remote-specific upload-pack settings when the read and write URLs agree.
    fetch_url = fetch.stdout.rstrip("\r\n")
    return tuple(dict.fromkeys(None if url == fetch_url else url for url in push.stdout.splitlines()))


def read_publication_receiver(
    repo: Path, remote: str, push_url: str | None, args: list[str], ref: str, command_runner: Callable[..., Any],
) -> subprocess.CompletedProcess:
    """Run ls-remote or fetch against the same endpoint that will receive the push."""
    from blackhole_agent.unbound import run_command

    env = None
    if push_url is not None:
        # Read the expanded push URL verbatim, even if it resembles a remote name
        # or matches another insteadOf rule. Preserve existing per-command config.
        remote = f"blackhole-receiver-{uuid.uuid4().hex}:"
        env = os.environ.copy()
        index = int(env.get("GIT_CONFIG_COUNT") or 0)
        env.update({
            "GIT_CONFIG_COUNT": str(index + 1),
            f"GIT_CONFIG_KEY_{index}": f"url.{push_url}.insteadOf",
            f"GIT_CONFIG_VALUE_{index}": remote,
        })
    return run_command(["git", *args, "--", remote, ref], cwd=repo, env=env, command_runner=command_runner, check=False)


def acquire_receiver_head(
    repo: Path, remote: str, branch: str, head: str, push_url: str | None, command_runner: Callable[..., Any],
) -> str:
    """Obtain a missing advertised commit without changing local refs, index or FETCH_HEAD."""
    from blackhole_agent.unbound import git_commit_exists, remote_branch_head

    if not head or git_commit_exists(repo, head, command_runner=command_runner):
        return ""
    failure = f"{RECEIVER_FETCH_ERROR} {head}"
    try:
        fetched = read_publication_receiver(
            repo, remote, push_url,
            ["fetch", "--no-tags", "--no-prune", "--no-prune-tags", "--no-recurse-submodules",
             "--no-write-fetch-head", "--no-auto-maintenance", "--refmap="],
            head, command_runner,
        )
        if fetched.returncode or not git_commit_exists(repo, head, command_runner=command_runner):
            return f"{failure}: {(fetched.stderr or fetched.stdout or '').strip() or 'commit unavailable'}"
        current, error = remote_branch_head(repo, remote, branch, push_url=push_url, command_runner=command_runner)
    except subprocess.TimeoutExpired as exc:
        return f"{failure}: timed out after {exc.timeout}s"
    except OSError as exc:
        return f"{failure}: {exc}"
    if error:
        return f"{failure}: {error}"
    if current != head:
        return f"Receiving branch changed during fetch: expected {head}, observed {current or '(missing)'}"
    return ""


def apply_publication_failure(loop_state: dict[str, Any], error: str) -> dict[str, Any]:
    """Record a failed publish; a terminal refusal must not retry forever."""

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


def integrate_clean_divergence(
    repo_path: Path,
    remote_head: str,
    lineage_tip: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> str:
    """Write a two-parent merge object without touching the publisher's checkout."""
    from blackhole_agent.registry_publication import publication_tree
    from blackhole_agent.unbound import run_command

    def git(*args: str, **options: Any) -> subprocess.CompletedProcess:
        return run_command(["git", *args], cwd=repo_path, command_runner=command_runner, **options)

    if not remote_head or not lineage_tip:
        return ""
    tree = publication_tree(git, remote_head, lineage_tip)
    if not tree:
        return ""
    return git(
        "commit-tree", tree, "-p", remote_head, "-p", lineage_tip,
        "-m", "Integrate a clean remote sibling with the proved lineage",
    ).stdout.strip()


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=repo, text=True, stderr=subprocess.PIPE).strip()


def _commit_file(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text + "\n", encoding="utf-8")
    _git(repo, "add", "--", name)
    _git(repo, "commit", "-qm", text)
    return _git(repo, "rev-parse", "HEAD")


def builtin_publication_resilience_proof() -> dict[str, Any]:
    """Exercise publication, refusal and retry against independent local Git repositories."""

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

    with tempfile.TemporaryDirectory(prefix="publication-peers-") as tmp:
        root = Path(tmp)
        repo, remote, peer = (root / name for name in ("repo", "remote.git", "peer"))
        _git(root, "init", "-qb", "main", str(repo))
        _git(repo, "config", "user.email", "pub@test.local")
        _git(repo, "config", "user.name", "Pub Test")
        seed = _commit_file(repo, "README.md", "seed")
        _git(root, "init", "--bare", str(remote))
        _git(repo, "remote", "add", "origin", remote.as_posix())
        pushes: list[list[str]] = []

        def record(command, **kwargs):
            if "push" in command:
                pushes.append(command)
            return subprocess.run(command, **kwargs)

        created = publish_lineage(repo, seed, remote.as_posix(), "main")
        checks["empty_remote_creates_branch"] = (
            created.ok and created.remote_before == "" and created.remote_after == seed
        )
        tip = _commit_file(repo, "advance.txt", "next")
        published = publish_lineage(repo, tip, "origin", "main", command_runner=record)
        checks["ancestor_fast_forward_publishes"] = (
            published.ok
            and published.remote_before == seed
            and published.remote_after == tip
            and remote_head_is_fast_forward(repo, seed, tip)
            and bool(pushes)
        )
        pushes.clear()
        republished = publish_lineage(repo, tip, "origin", "main", command_runner=record)
        checks["same_sha_republication_is_idempotent"] = (
            republished.ok and republished.remote_before == republished.remote_after == tip and not pushes
        )
        checks["remote_head_matches_tip"] = _git(remote, "rev-parse", "main") == tip

        _git(
            root, "clone", "--no-local", "-b", "main", "-c", "user.name=Peer", "-c", "user.email=peer@test.local",
            remote.as_posix(), str(peer),
        )
        remote_tip = _commit_file(peer, "remote-only.txt", "remote")
        _git(peer, "push", "origin", "main")
        local_tip = _commit_file(repo, "local.txt", "local")
        pushes.clear()
        integrated = publish_lineage(repo, local_tip, "origin", "main", command_runner=record)
        merged = integrated.remote_after
        checks["diverged_clean_merge_publishes"] = (
            integrated.ok
            and integrated.remote_before == remote_tip
            and _git(remote, "show", "-s", "--format=%P", merged).split() == [remote_tip, local_tip]
            and _git(remote, "show", f"{merged}:remote-only.txt") == "remote"
            and _git(remote, "show", f"{merged}:local.txt") == "local"
            and bool(pushes)
            and not any("--force" in item or "--force-with-lease" in item for item in pushes)
        )
        checks["diverged_clean_merge_fast_forwards"] = (
            _git(remote, "rev-parse", "main") == merged and remote_head_is_fast_forward(repo, remote_tip, merged)
        )
        checks["unknown_remote_sha_is_not_ancestor"] = (
            remote_head_is_fast_forward(repo, remote_tip, local_tip) is False
            and remote_head_is_fast_forward(repo, "0" * 40, local_tip) is False
        )

        remote_tip = _commit_file(peer, "shared.txt", "remote")
        _git(peer, "push", "origin", "HEAD:refs/heads/conflict")
        local_tip = _commit_file(repo, "shared.txt", "local")
        pushes.clear()
        refused = publish_lineage(repo, local_tip, "origin", "conflict", command_runner=record)
        checks["conflicting_divergence_is_refused"] = (
            not refused.ok and is_remote_head_mismatch(refused.error)
            and refused.remote_before == remote_tip and not pushes
        )
        checks["conflicting_remote_is_unchanged"] = _git(remote, "rev-parse", "conflict") == remote_tip

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
        register_catalog_proved(root, PUBLICATION_RESILIENCE_ID)
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
        from blackhole_agent.mission_selection import assess_mission_selection

        gate = assess_mission_selection(root, PUBLICATION_RESILIENCE_GOAL, PUBLICATION_RESILIENCE_DONE_WHEN, history=[])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_rejects_ledger_only_publication"] = (
        not gate.accepted
        and live_goal != PUBLICATION_RESILIENCE_GOAL
        and PUBLICATION_RESILIENCE_ID not in live_done
        and live_source != "genesis_bind_publication"
    )
    checks["exhausted_catalog_stays_unbound_without_gate_passing_successor"] = (
        (live_goal, live_done, live_source) == ("", "", "")
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
