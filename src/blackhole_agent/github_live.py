"""Live GitHub actuation: real issue -> branch -> tested fix -> merged PR.

This module extends the live-actuation lineage (MCP stdio sessions, external
third-party MCP servers) to the world's dominant code platform. One run drives
a complete software-engineering change against real GitHub through the
authenticated ``gh`` CLI:

    auth check -> ensure private sandbox repo -> seed a real bug + check script
    -> open a real issue -> branch -> apply fix -> run the check locally
    -> push -> open PR (Closes #N) -> squash merge -> verify the issue is
    CLOSED and merged main contains the fix -> seal a digest-chained trace.

The sealed trace is re-verifiable offline and tamper-falsifiable, matching the
evidence contract established by ``mcp_client``. The proof command is live by
default: every proof run performs a fresh, unique end-to-end change, so the
capability cannot silently degrade into replayed evidence.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso

SCHEMA_VERSION = 1
DEFAULT_SANDBOX_REPO = "blackhole-agent-live-sandbox"

BUG_CALC = "def add(a, b):\n    return a - b  # BUG: subtraction shipped as add\n"
FIX_CALC = "def add(a, b):\n    return a + b\n"
CHECK_SCRIPT = (
    "from calc import add\n"
    "\n"
    "assert add(2, 3) == 5, 'add(2, 3) must be 5'\n"
    "assert add(-1, 1) == 0, 'add(-1, 1) must be 0'\n"
    "assert add(0, 0) == 0, 'add(0, 0) must be 0'\n"
    "print('check ok')\n"
)


class GitHubLiveError(RuntimeError):
    """Raised when a live GitHub actuation step fails."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    import hashlib

    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def gh_command() -> str | None:
    """Path to the GitHub CLI, or None when it is not installed."""

    return shutil.which("gh")


def _run(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    proc = subprocess.run(
        [str(part) for part in argv],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _gh(args: Sequence[str], *, timeout_seconds: float = 120.0) -> dict[str, Any]:
    gh = gh_command()
    if gh is None:
        raise GitHubLiveError("gh CLI is not installed")
    return _run([gh, *args], timeout_seconds=timeout_seconds)


def _require(result: Mapping[str, Any], step: str) -> dict[str, Any]:
    if not result.get("ok"):
        raise GitHubLiveError(f"{step} failed: {result.get('stderr') or result.get('stdout')}")
    return dict(result)


def authenticated_login() -> str:
    """Login of the authenticated GitHub account (fails when not logged in)."""

    result = _require(_gh(["api", "user", "--jq", ".login"]), "gh api user")
    return str(result["stdout"])


def ensure_sandbox_repo(full_name: str) -> dict[str, Any]:
    """Return sandbox repo state; create the private repo when it is missing."""

    view = _gh(["repo", "view", full_name, "--json", "nameWithOwner,isPrivate,defaultBranchRef"])
    if view["ok"]:
        payload = json.loads(view["stdout"])
        return {
            "created": False,
            "full_name": payload["nameWithOwner"],
            "private": bool(payload.get("isPrivate")),
            "default_branch": (payload.get("defaultBranchRef") or {}).get("name") or "main",
        }
    _require(_gh(["repo", "create", full_name, "--private"]), "gh repo create")
    return {"created": True, "full_name": full_name, "private": True, "default_branch": "main"}


def _put_file(full_name: str, path: str, content: str, message: str) -> None:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    _require(
        _gh(
            [
                "api",
                f"repos/{full_name}/contents/{path}",
                "-X",
                "PUT",
                "-f",
                f"message={message}",
                "-f",
                f"content={encoded}",
            ]
        ),
        f"seed {path}",
    )


def seed_bug_files(full_name: str) -> dict[str, Any]:
    """Seed the buggy calculator + check script; skip when calc.py exists."""

    probe = _gh(["api", f"repos/{full_name}/contents/calc.py"])
    if probe["ok"]:
        return {"seeded": False}
    _put_file(full_name, "calc.py", BUG_CALC, "chore: seed calculator (intentional add bug)")
    _put_file(full_name, "check.py", CHECK_SCRIPT, "chore: seed check script")
    return {"seeded": True}


def run_live_change(
    *,
    repo_name: str = DEFAULT_SANDBOX_REPO,
    output_dir: Path | None = None,
    recorded_at: str | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Run one full live change against real GitHub and seal the trace."""

    gh = gh_command()
    if gh is None:
        raise GitHubLiveError("gh CLI is not installed")

    sentinel = uuid.uuid4().hex[:12]
    login = authenticated_login()
    full_name = repo_name if "/" in repo_name else f"{login}/{repo_name}"

    repo = ensure_sandbox_repo(full_name)
    seed = seed_bug_files(full_name)

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="github-live-"))
    out.mkdir(parents=True, exist_ok=True)
    workdir = out / "worktree"
    _require(_gh(["repo", "clone", full_name, str(workdir), "--", "--depth", "1"]), "gh repo clone")

    def git(*args: str) -> dict[str, Any]:
        return _require(_run(["git", *args], cwd=workdir), f"git {' '.join(args)}")

    git("config", "user.name", "blackhole-unbound")
    git("config", "user.email", "blackhole-unbound@localhost")

    # Repeat runs must re-face a real bug: a previous merged cycle left the fix
    # on main, so reintroduce the bug on main before opening the issue.
    bug_reintroduced = False
    if "return a - b" not in (workdir / "calc.py").read_text(encoding="utf-8"):
        (workdir / "calc.py").write_text(BUG_CALC, encoding="utf-8")
        git("add", "calc.py")
        git("commit", "-m", f"chore: reintroduce add bug for live probe {sentinel}")
        git("push", "origin", f"HEAD:{repo['default_branch']}")
        bug_reintroduced = True

    # Falsifiable baseline: the shipped bug must fail the check script.
    bug_check = _run([sys.executable, "-B", "check.py"], cwd=workdir)

    issue_title = f"add() subtracts instead of adding [{sentinel}]"
    issue = _require(
        _gh(
            [
                "issue",
                "create",
                "--repo",
                full_name,
                "--title",
                issue_title,
                "--body",
                "Live actuation probe: `calc.add` returns `a - b`. "
                "Fix so `check.py` passes. Seeded by blackhole-unbound "
                f"sentinel {sentinel}.",
            ]
        ),
        "gh issue create",
    )
    issue_url = issue["stdout"].strip()
    issue_number = int(issue_url.rstrip("/").rsplit("/", 1)[-1])

    branch = f"fix/add-{sentinel}"
    git("checkout", "-b", branch)
    (workdir / "calc.py").write_text(FIX_CALC, encoding="utf-8")
    fix_check = _run([sys.executable, "-B", "check.py"], cwd=workdir)
    if not fix_check["ok"]:
        raise GitHubLiveError(f"local fix check failed: {fix_check['stderr'] or fix_check['stdout']}")

    git("add", "calc.py")
    git("commit", "-m", f"fix: add() must sum, not subtract\n\nCloses #{issue_number}")
    git("push", "-u", "origin", branch)

    pr = _require(
        _gh(
            [
                "pr",
                "create",
                "--repo",
                full_name,
                "--title",
                f"fix: add() must sum [{sentinel}]",
                "--body",
                f"Closes #{issue_number}\n\nLive actuation by blackhole-unbound; "
                f"local check.py passed before push. Sentinel {sentinel}.",
                "--head",
                branch,
            ]
        ),
        "gh pr create",
    )
    pr_url = pr["stdout"].strip()
    pr_number = int(pr_url.rstrip("/").rsplit("/", 1)[-1])

    _require(
        _gh(["pr", "merge", str(pr_number), "--repo", full_name, "--squash", "--delete-branch"]),
        "gh pr merge",
    )

    issue_state = _require(
        _gh(["issue", "view", str(issue_number), "--repo", full_name, "--json", "state"]),
        "gh issue view",
    )
    pr_state = _require(
        _gh(["pr", "view", str(pr_number), "--repo", full_name, "--json", "state,mergedAt"]),
        "gh pr view",
    )
    merged_calc = _require(
        _gh(["api", f"repos/{full_name}/contents/calc.py?ref=main", "--jq", ".content"]),
        "read merged calc.py",
    )
    merged_source = base64.b64decode(merged_calc["stdout"].replace("\n", "")).decode("utf-8")

    outcome = {
        "sentinel": sentinel,
        "repo": full_name,
        "repo_created": repo["created"],
        "seeded_bug_files": seed["seeded"],
        "bug_reintroduced_on_main": bug_reintroduced,
        "bug_check_failed_before_fix": not bug_check["ok"],
        "fix_check": {"ok": fix_check["ok"], "stdout": fix_check["stdout"]},
        "issue": {"number": issue_number, "url": issue_url, "state": json.loads(issue_state["stdout"]).get("state")},
        "pr": {
            "number": pr_number,
            "url": pr_url,
            "state": json.loads(pr_state["stdout"]).get("state"),
            "merged_at": json.loads(pr_state["stdout"]).get("mergedAt"),
        },
        "merged_main_contains_fix": "return a + b" in merged_source,
    }

    stages = {
        "auth": {"login": login},
        "repo": repo,
        "seed": seed,
        "bug_reintroduced_on_main": bug_reintroduced,
        "bug_baseline": {"ok": bug_check["ok"], "returncode": bug_check["returncode"]},
        "issue": outcome["issue"],
        "fix_check": outcome["fix_check"],
        "pr": outcome["pr"],
        "merged_main_contains_fix": outcome["merged_main_contains_fix"],
    }
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "github_live_change_trace",
        "recorded_at": recorded_at or utc_now_iso(),
        "sentinel": sentinel,
        "repo": full_name,
        "stages": stages,
        "stages_digest": _digest(stages),
        "outcome": outcome,
        "outcome_digest": _digest(outcome),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    atomic_write_json(out / "change.json", trace)
    return {
        "ok": True,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "outcome": outcome,
    }


def verify_change_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed live-change trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "change.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing change trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    outcome = trace.get("outcome") or {}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "stages_digest": _digest(trace.get("stages")) == trace.get("stages_digest"),
        "outcome_digest": _digest(outcome) == trace.get("outcome_digest"),
        "bug_failed_before_fix": outcome.get("bug_check_failed_before_fix") is True,
        "fix_check_passed": (outcome.get("fix_check") or {}).get("ok") is True,
        "pr_merged": (outcome.get("pr") or {}).get("state") == "MERGED"
        and bool((outcome.get("pr") or {}).get("merged_at")),
        "issue_closed": (outcome.get("issue") or {}).get("state") == "CLOSED",
        "merged_main_contains_fix": outcome.get("merged_main_contains_fix") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def builtin_github_live_actuation_proof() -> dict[str, Any]:
    """Registered proof for ``capability.github-live-actuation``.

    Performs a fresh, unique end-to-end change against real GitHub: private
    sandbox repo ensured, real bug seeded, real issue opened, fix branch
    pushed after the local check passes, real PR merged with squash, issue
    auto-closed via ``Closes #N``, merged main re-read through the API. The
    sealed trace is re-verified, a tampered copy must fail verification, and a
    ``gh repo view`` against a nonexistent repo must fail closed.
    """

    if gh_command() is None:
        return {"ok": False, "error": "gh CLI is not installed"}

    with tempfile.TemporaryDirectory(prefix="github-live-proof-") as tmp:
        out = Path(tmp) / "live"
        try:
            run = run_live_change(output_dir=out)
        except (GitHubLiveError, subprocess.TimeoutExpired) as error:
            return {"ok": False, "error": f"live change failed: {error}"}
        verify = verify_change_trace(out)

        # Tamper falsification: an edited recorded outcome must fail.
        clone = Path(tmp) / "tampered"
        shutil.copytree(out, clone)
        trace = json.loads((clone / "change.json").read_text(encoding="utf-8"))
        trace["outcome"]["pr"]["state"] = "OPEN"
        atomic_write_json(clone / "change.json", trace)
        tampered = verify_change_trace(clone)

        # Fail closed: viewing a repo that cannot exist must error.
        ghost = _gh(["repo", "view", f"{run['outcome']['repo'].split('/')[0]}/no-such-repo-{uuid.uuid4().hex}"])
        fail_closed = not ghost["ok"]

    outcome = run.get("outcome") or {}
    ok = (
        run["ok"]
        and verify["ok"]
        and not tampered["ok"]
        and fail_closed
        and outcome.get("merged_main_contains_fix") is True
    )
    return {
        "ok": bool(ok),
        "trace_digest": run.get("trace_digest"),
        "repo": outcome.get("repo"),
        "issue_url": (outcome.get("issue") or {}).get("url"),
        "pr_url": (outcome.get("pr") or {}).get("url"),
        "issue_auto_closed": (outcome.get("issue") or {}).get("state") == "CLOSED",
        "pr_merged": (outcome.get("pr") or {}).get("state") == "MERGED",
        "bug_baseline_falsified": outcome.get("bug_check_failed_before_fix") is True,
        "trace_verified": verify["ok"],
        "tamper_falsified": not tampered["ok"],
        "ghost_repo_fail_closed": fail_closed,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live GitHub actuation with sealed evidence")
    sub = parser.add_subparsers(dest="command_name", required=True)

    execute = sub.add_parser("execute", help="Run one full live change and seal the trace")
    execute.add_argument("--repo", default=DEFAULT_SANDBOX_REPO, help="Sandbox repo name or owner/name")
    execute.add_argument("--output-dir", default=None)

    verify = sub.add_parser("verify", help="Re-verify a sealed change trace")
    verify.add_argument("--trace-dir", required=True)

    sub.add_parser("proof", help="Run the registered capability proof")

    args = parser.parse_args(argv)
    if args.command_name == "execute":
        result = run_live_change(repo_name=args.repo, output_dir=Path(args.output_dir) if args.output_dir else None)
    elif args.command_name == "verify":
        result = verify_change_trace(Path(args.trace_dir))
    else:
        result = builtin_github_live_actuation_proof()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
