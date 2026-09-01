"""Drive a first-class GitHub tool through an issue-gated pull-request workflow.

Tool routing already fails missions that require ``github``: hosted code-platform
plugins stay on the unsupported MCP provider, and no first-party GitHub
provider is executable. Unbound therefore cannot search, label, or seal a
pull request on an open issue.

This module closes that hole:

- advertise a ``github`` provider tool that stays fail-closed until opted in
- drive search / label / open-PR against an in-process repository fixture
- keep an unauthenticated client so the auth hole stays falsifiable
- refuse pull requests until the open issue carries the triage label
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor after CDP
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

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
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    GITHUB_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    github_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GITHUB_ACTUATION_ID = "capability.github-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-github"
SENTINEL = "BH-GITHUB-OK"
TRIAGE_LABEL = "BH-TRIAGE"
OPEN_ISSUE_NUMBER = 1
OPEN_ISSUE_TITLE = "operator-triage"
OPEN_ISSUE_BODY = "seal-me"
DEFAULT_PR_TITLE = "Close operator-triage"
DEFAULT_PR_BODY = SENTINEL
DEFAULT_HEAD = "unbound/github-actuation"
DEFAULT_BASE = "main"

GITHUB_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GITHUB_ACTUATION_ID};"
    f"capability_proved:{GITHUB_ACTUATION_ID};"
    "no_skill_route"
)
GITHUB_ACTUATION_GOAL = (
    "Repair GitHub issue-gated pull request actuation: hosted code-platform "
    "tools remain unsupported so an open issue cannot be labelled and a sealed "
    "pull request cannot be produced. Unauthenticated issue search stays "
    "forbidden; fail-closed routing never opts the github provider in."
)


class GithubActuationError(RuntimeError):
    """Raised when the repository session or fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass
class RepoIssue:
    number: int
    title: str
    body: str
    state: str = "open"
    labels: list[str] = field(default_factory=list)


@dataclass
class RepoPullRequest:
    number: int
    title: str
    body: str
    head: str
    base: str
    closes: int
    merged: bool = False


class GithubSession:
    """Auth-gated in-process GitHub repo: search, label, open PR, read."""

    def __init__(self, *, authed: bool = True) -> None:
        self.authed = bool(authed)
        self.labels: dict[str, str] = {"bug": "bug"}
        self.issues: dict[int, RepoIssue] = {
            OPEN_ISSUE_NUMBER: RepoIssue(
                number=OPEN_ISSUE_NUMBER,
                title=OPEN_ISSUE_TITLE,
                body=OPEN_ISSUE_BODY,
                state="open",
                labels=["bug"],
            )
        }
        self.pulls: list[RepoPullRequest] = []
        self.history: list[dict[str, Any]] = []

    def _forbidden(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 403,
            "error": reason,
            "matches": [],
            "pr_number": 0,
            "sentinel": "",
        }

    def _snapshot_issue(self, issue: RepoIssue) -> dict[str, Any]:
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "labels": list(issue.labels),
        }

    def _snapshot_pr(self, pull: RepoPullRequest) -> dict[str, Any]:
        return {
            "number": pull.number,
            "title": pull.title,
            "body": pull.body,
            "head": pull.head,
            "base": pull.base,
            "closes": pull.closes,
            "merged": pull.merged,
            "sentinel": SENTINEL if SENTINEL in pull.body else "",
        }

    def search(self, query: str) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        wanted = str(query or "").strip()
        matches: list[dict[str, Any]] = []
        for issue in self.issues.values():
            if _query_matches(wanted, issue):
                matches.append(self._snapshot_issue(issue))
        return {"ok": True, "status": 200, "matches": matches, "query": wanted}

    def list_labels(self) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        return {
            "ok": True,
            "status": 200,
            "labels": [{"id": key, "name": name} for key, name in sorted(self.labels.items())],
        }

    def add_label(self, issue_number: int, *, labels: list[str] | None = None) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        issue = self.issues.get(int(issue_number or 0))
        if issue is None:
            return {"ok": False, "status": 404, "error": "missing_issue", "matches": []}
        for label in labels or []:
            name = str(label or "").strip()
            if not name:
                continue
            self.labels.setdefault(name, name)
            if name not in issue.labels:
                issue.labels.append(name)
        return {"ok": True, "status": 200, "issue": self._snapshot_issue(issue)}

    def create_pr(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
        closes: int,
    ) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        issue = self.issues.get(int(closes or 0))
        if issue is None:
            return {"ok": False, "status": 404, "error": "missing_issue"}
        if TRIAGE_LABEL not in issue.labels:
            return self._forbidden("label_gated")
        if issue.state != "open":
            return {"ok": False, "status": 409, "error": "issue_closed"}
        text = str(body or "")
        if f"Closes #{issue.number}" not in text:
            text = f"{text}\n\nCloses #{issue.number}".strip()
        pull = RepoPullRequest(
            number=len(self.pulls) + 1,
            title=str(title or ""),
            body=text,
            head=str(head or DEFAULT_HEAD),
            base=str(base or DEFAULT_BASE),
            closes=issue.number,
        )
        self.pulls.append(pull)
        issue.state = "closed"
        return {
            "ok": True,
            "status": 201,
            "pr_number": pull.number,
            "body": pull.body,
            "sentinel": SENTINEL if SENTINEL in pull.body else "",
            "closes": issue.number,
            "labelled": True,
            "issue_state": issue.state,
        }

    def read_pr(self, pr_number: int = 0) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        if not self.pulls:
            return {"ok": False, "status": 404, "error": "missing_pr"}
        target = int(pr_number or 0)
        pull = self.pulls[target - 1] if 1 <= target <= len(self.pulls) else self.pulls[-1]
        issue = self.issues.get(pull.closes)
        return {
            "ok": True,
            "status": 200,
            "pr": self._snapshot_pr(pull),
            "pr_number": pull.number,
            "body": pull.body,
            "sentinel": SENTINEL if SENTINEL in pull.body else "",
            "closes": pull.closes,
            "labelled": bool(issue and TRIAGE_LABEL in issue.labels),
            "issue_state": issue.state if issue else "",
        }


def _query_matches(query: str, issue: RepoIssue) -> bool:
    if not query:
        return True
    for token in query.split():
        lowered = token.lower()
        if lowered == "is:open" and issue.state != "open":
            return False
        if lowered == "is:closed" and issue.state != "closed":
            return False
        if lowered.startswith("label:"):
            wanted = token.split(":", 1)[1]
            if wanted not in issue.labels:
                return False
        elif lowered.startswith("title:"):
            wanted = token.split(":", 1)[1].lower()
            if wanted not in issue.title.lower():
                return False
        elif lowered not in {
            issue.title.lower(),
            issue.body.lower(),
            *{item.lower() for item in issue.labels},
        } and not lowered.startswith(("is:", "label:", "title:")):
            if lowered not in f"{issue.title} {issue.body}".lower():
                return False
    return True


def call_github_tool(session: GithubSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one github tool call against an open repository session."""

    action = str(arguments.get("action") or "").strip()
    if action == "search":
        result = session.search(str(arguments.get("query") or ""))
    elif action == "list_labels":
        result = session.list_labels()
    elif action == "add_label":
        labels = arguments.get("labels") or arguments.get("addLabelIds") or []
        if isinstance(labels, str):
            labels = [labels]
        result = session.add_label(
            int(arguments.get("issueNumber") or arguments.get("number") or 0),
            labels=[str(item) for item in labels],
        )
    elif action == "create_pr":
        result = session.create_pr(
            title=str(arguments.get("title") or DEFAULT_PR_TITLE),
            body=str(arguments.get("body") or DEFAULT_PR_BODY),
            head=str(arguments.get("head") or DEFAULT_HEAD),
            base=str(arguments.get("base") or DEFAULT_BASE),
            closes=int(arguments.get("closes") or OPEN_ISSUE_NUMBER),
        )
    elif action == "read_pr":
        result = session.read_pr(int(arguments.get("prNumber") or arguments.get("number") or 0))
    else:
        raise GithubActuationError(f"unsupported github action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def run_github_workflow(
    *,
    authed: bool = True,
    body: str = DEFAULT_PR_BODY,
    output_dir: Path | None = None,
    skip_label: bool = False,
) -> dict[str, Any]:
    """Execute the label-gated search-label-PR workflow and seal a trace."""

    descriptor = github_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GITHUB_TOOL_PROVIDER),
    )
    routing = {
        "descriptor": {
            "name": descriptor.name,
            "provider": descriptor.provider,
            "tool_type": descriptor.tool_type,
        },
        "route": decision.route,
        "reasons": list(decision.reasons),
        "executable": decision.executable,
    }
    if not decision.executable:
        raise GithubActuationError(f"github tool did not route executable: {decision.reasons}")

    session = GithubSession(authed=authed)
    calls: list[dict[str, Any]] = [
        {"action": "search", "query": "is:open"},
        {"action": "list_labels"},
    ]
    if not skip_label:
        calls.append(
            {
                "action": "add_label",
                "issueNumber": OPEN_ISSUE_NUMBER,
                "labels": [TRIAGE_LABEL],
            }
        )
    calls.extend(
        [
            {
                "action": "create_pr",
                "title": DEFAULT_PR_TITLE,
                "body": body,
                "head": DEFAULT_HEAD,
                "base": DEFAULT_BASE,
                "closes": OPEN_ISSUE_NUMBER,
            },
            {"action": "read_pr"},
        ]
    )
    results: list[dict[str, Any]] = []
    for arguments in calls:
        try:
            results.append(call_github_tool(session, arguments))
        except GithubActuationError as error:
            results.append({"action": arguments["action"], "error": str(error)})
            break
        if int(results[-1].get("status") or 0) >= 400:
            break

    final = results[-1] if results else {}
    labelled = False
    issue = session.issues.get(OPEN_ISSUE_NUMBER)
    if issue is not None:
        labelled = TRIAGE_LABEL in issue.labels
    pr_body = str(final.get("body") or "")
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "github_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "authed": authed,
        "skip_label": skip_label,
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "sentinel": str(final.get("sentinel") or ""),
        "pr_body": pr_body,
        "pr_number": int(final.get("pr_number") or 0),
        "labelled": labelled,
        "issue_state": str(final.get("issue_state") or (issue.state if issue else "")),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="github-live-"))
    out.mkdir(parents=True, exist_ok=True)
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    sealed = bool(
        decision.executable
        and authed
        and not skip_label
        and labelled
        and str(final.get("sentinel") or "") == SENTINEL
        and SENTINEL in pr_body
        and f"Closes #{OPEN_ISSUE_NUMBER}" in pr_body
        and str(final.get("issue_state") or "") == "closed"
    )
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sentinel": str(final.get("sentinel") or ""),
        "pr_body": pr_body,
        "pr_number": int(final.get("pr_number") or 0),
        "final_status": int(final.get("status") or 0),
        "authed": authed,
        "labelled": labelled,
        "issue_state": str(final.get("issue_state") or ""),
        "error": str(final.get("error") or ""),
        "match_count": len((results[0].get("matches") if results else []) or []),
    }


def verify_github_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed GitHub trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    pr_body = str(trace.get("pr_body") or "")
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "pr_recorded": SENTINEL in pr_body and f"Closes #{OPEN_ISSUE_NUMBER}" in pr_body,
        "labelled": trace.get("labelled") is True,
        "issue_closed": trace.get("issue_state") == "closed",
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def github_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.github_actuation import "
        "builtin_github_actuation_proof; r=builtin_github_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='github_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_github_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GITHUB_ACTUATION_ID,
        name="First-class GitHub issue-gated PR actuation",
        description=(
            "Missions that require a GitHub tool can opt the github provider in, "
            "search an open issue, apply a triage label, and seal a digest-chained "
            "pull request. Default routing stays fail-closed; an unauthenticated "
            "client keeps the auth hole falsifiable, and PRs stay label-gated."
        ),
        kind="python",
        entry="blackhole_agent.github_actuation:builtin_github_actuation_proof",
        proof_command=github_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.browser-cdp-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/github_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required GitHub tool is executable after explicit provider opt-in: "
            "Unbound searches an open issue, applies a triage label, seals a "
            "tamper-evident pull request that closes the issue, and binds this "
            "family as the next diversity-catalog successor once CDP actuation "
            "is proved."
        ),
        tags=("github", "issue", "pull-request", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T032535Z-cf8eef0c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_github_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in GitHub actuation seals a label-gated pull request."""

    from blackhole_agent.browser_cdp_actuation import BROWSER_CDP_GOAL, BROWSER_CDP_ID
    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import capability_family

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = GITHUB_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GITHUB_ACTUATION_GOAL) == (
        GITHUB_ACTUATION_ID,
    )
    checks["gmail_goal_is_not_github"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["cdp_goal_is_not_github"] = leftover_marker_ids(BROWSER_CDP_GOAL) == (
        BROWSER_CDP_ID,
    )
    checks["github_goal_is_not_gmail"] = GMAIL_ACTUATION_ID not in leftover_marker_ids(
        GITHUB_ACTUATION_GOAL
    )
    checks["github_goal_is_not_cdp"] = BROWSER_CDP_ID not in leftover_marker_ids(
        GITHUB_ACTUATION_GOAL
    )
    checks["gmail_marker_stays_gmail"] = GITHUB_ACTUATION_ID not in leftover_marker_ids(
        GMAIL_ACTUATION_GOAL
    )
    checks["cdp_marker_stays_cdp"] = GITHUB_ACTUATION_ID not in leftover_marker_ids(
        BROWSER_CDP_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_github"] = (
        len(catalog) > 24
        and catalog[24]["id"] == GITHUB_ACTUATION_ID
        and catalog[23]["id"] == BROWSER_CDP_ID
    )
    checks["family_is_git_publication"] = "git-publication" in capability_family(
        GITHUB_ACTUATION_GOAL
    )

    mcp_github = ToolDescriptor(name="remote_github", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_github)
    checks["naive_mcp_github_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = github_tool_descriptor()
    default_github = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GITHUB_TOOL_PROVIDER),
    )
    checks["default_github_provider_is_unsupported"] = (
        default_github.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{GITHUB_TOOL_PROVIDER}" in default_github.reasons
    )
    checks["opted_in_github_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_github],
        required_tool_names=("local_memory", "github"),
    )
    checks["naive_preflight_missing_github"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["github"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "github"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GITHUB_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "github" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="github-actuation-") as tmp:
        root = Path(tmp)
        naive = run_github_workflow(authed=False, output_dir=root / "naive")
        unlabeled = run_github_workflow(skip_label=True, output_dir=root / "unlabeled")
        live = run_github_workflow(output_dir=root / "live")
        verify = verify_github_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_github_trace(clone)
        checks["naive_without_auth_is_forbidden"] = (
            naive["ok"] is False
            and naive["sentinel"] == ""
            and naive["final_status"] == 403
            and naive["error"] == "unauthenticated"
        )
        checks["unlabelled_pr_is_forbidden"] = (
            unlabeled["ok"] is False
            and unlabeled["final_status"] == 403
            and unlabeled["error"] == "label_gated"
            and unlabeled["labelled"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_seals_pull_request"] = SENTINEL in live["pr_body"]
        checks["workflow_closes_labelled_issue"] = (
            live["labelled"] is True and live["issue_state"] == "closed"
        )
        checks["auth_and_label_are_required"] = (
            naive["ok"] is False and unlabeled["ok"] is False and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="github-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != GITHUB_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_github"] = (
        live_goal == GITHUB_ACTUATION_GOAL
        and GITHUB_ACTUATION_ID in live_done
        and live_source == "genesis_bind_github"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_github_actuation_capability()
    return {
        "ok": ok,
        "action": "github_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GITHUB_ACTUATION_GOAL,
        "done_when": GITHUB_ACTUATION_DONE_WHEN,
    }
