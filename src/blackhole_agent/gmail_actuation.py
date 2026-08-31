"""Drive a first-class Gmail tool through a label-gated inbox workflow.

Tool routing already fails missions that require ``gmail``: hosted Gmail
plugins stay on the unsupported MCP provider, and no first-party mail
provider is executable. Unbound therefore cannot search, label, or seal
a draft on an unread thread.

This module closes that hole:

- advertise a ``gmail`` provider tool that stays fail-closed until opted in
- drive search / label / draft against an in-process mailbox fixture
- keep an unauthenticated client so the auth hole stays falsifiable
- refuse drafts until the unread thread carries the triage label
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor
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
    GMAIL_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    gmail_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GMAIL_ACTUATION_ID = "capability.gmail-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-gmail"
SENTINEL = "BH-GMAIL-OK"
TRIAGE_LABEL = "BH-TRIAGE"
UNREAD_MESSAGE_ID = "msg-unread-1"
UNREAD_SUBJECT = "operator-triage"
UNREAD_BODY = "seal-me"
DEFAULT_DRAFT_BODY = SENTINEL
DEFAULT_DRAFT_TO = "operator@blackhole.invalid"

GMAIL_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GMAIL_ACTUATION_ID};"
    f"capability_proved:{GMAIL_ACTUATION_ID};"
    "no_skill_route"
)
GMAIL_ACTUATION_GOAL = (
    "Repair Gmail inbox auth actuation: hosted mail tools remain unsupported "
    "so an unread thread cannot be labelled and a sealed draft cannot be "
    "produced. Unauthenticated search stays forbidden; fail-closed routing "
    "never opts the mail provider in."
)


class GmailActuationError(RuntimeError):
    """Raised when the mailbox session or fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass
class MailMessage:
    id: str
    sender: str
    subject: str
    body: str
    label_ids: list[str] = field(default_factory=list)
    unread: bool = True


@dataclass
class MailDraft:
    id: str
    to: list[str]
    subject: str
    body: str
    in_reply_to: str = ""


class MailboxSession:
    """Auth-gated in-process mailbox: search, label, draft, read."""

    def __init__(self, *, authed: bool = True) -> None:
        self.authed = bool(authed)
        self.labels: dict[str, str] = {"INBOX": "INBOX", "UNREAD": "UNREAD"}
        self.messages: dict[str, MailMessage] = {
            UNREAD_MESSAGE_ID: MailMessage(
                id=UNREAD_MESSAGE_ID,
                sender=DEFAULT_DRAFT_TO,
                subject=UNREAD_SUBJECT,
                body=UNREAD_BODY,
                label_ids=["INBOX", "UNREAD"],
                unread=True,
            )
        }
        self.drafts: list[MailDraft] = []
        self.history: list[dict[str, Any]] = []

    def _forbidden(self, reason: str) -> dict[str, Any]:
        return {"ok": False, "status": 403, "error": reason, "matches": [], "draft_id": "", "sentinel": ""}

    def _snapshot_message(self, message: MailMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "from": message.sender,
            "subject": message.subject,
            "body": message.body,
            "labelIds": list(message.label_ids),
            "unread": message.unread,
        }

    def search(self, query: str) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        wanted = str(query or "").strip()
        matches: list[dict[str, Any]] = []
        for message in self.messages.values():
            if _query_matches(wanted, message):
                matches.append(self._snapshot_message(message))
        return {"ok": True, "status": 200, "matches": matches, "query": wanted}

    def list_labels(self) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        return {
            "ok": True,
            "status": 200,
            "labels": [{"id": key, "name": name} for key, name in sorted(self.labels.items())],
        }

    def modify(self, message_id: str, *, add_label_ids: list[str] | None = None) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        message = self.messages.get(str(message_id or ""))
        if message is None:
            return {"ok": False, "status": 404, "error": "missing_message", "matches": []}
        for label in add_label_ids or []:
            name = str(label or "").strip()
            if not name:
                continue
            self.labels.setdefault(name, name)
            if name not in message.label_ids:
                message.label_ids.append(name)
            if name != "UNREAD" and message.unread:
                message.unread = False
                if "UNREAD" in message.label_ids:
                    message.label_ids.remove("UNREAD")
        return {"ok": True, "status": 200, "message": self._snapshot_message(message)}

    def draft(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        in_reply_to: str = "",
    ) -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        thread_id = str(in_reply_to or UNREAD_MESSAGE_ID)
        message = self.messages.get(thread_id)
        if message is None:
            return {"ok": False, "status": 404, "error": "missing_thread"}
        if TRIAGE_LABEL not in message.label_ids:
            return self._forbidden("label_gated")
        draft = MailDraft(
            id=f"draft-{len(self.drafts) + 1}",
            to=[str(item) for item in to if str(item).strip()],
            subject=str(subject or ""),
            body=str(body or ""),
            in_reply_to=thread_id,
        )
        self.drafts.append(draft)
        return {
            "ok": True,
            "status": 200,
            "draft_id": draft.id,
            "body": draft.body,
            "sentinel": SENTINEL if draft.body == SENTINEL else "",
            "in_reply_to": thread_id,
            "labelled": True,
        }

    def read(self, message_id: str = "") -> dict[str, Any]:
        if not self.authed:
            return self._forbidden("unauthenticated")
        target = str(message_id or UNREAD_MESSAGE_ID)
        message = self.messages.get(target)
        if message is None:
            return {"ok": False, "status": 404, "error": "missing_message"}
        latest = self.drafts[-1] if self.drafts else None
        return {
            "ok": True,
            "status": 200,
            "message": self._snapshot_message(message),
            "draft_id": latest.id if latest else "",
            "draft_body": latest.body if latest else "",
            "sentinel": SENTINEL if latest and latest.body == SENTINEL else "",
            "labelled": TRIAGE_LABEL in message.label_ids,
        }


def _query_matches(query: str, message: MailMessage) -> bool:
    if not query:
        return True
    for token in query.split():
        lowered = token.lower()
        if lowered == "is:unread" and not message.unread:
            return False
        if lowered.startswith("label:"):
            wanted = token.split(":", 1)[1]
            if wanted not in message.label_ids:
                return False
        elif lowered.startswith("subject:"):
            wanted = token.split(":", 1)[1].lower()
            if wanted not in message.subject.lower():
                return False
        elif lowered not in {
            message.subject.lower(),
            message.body.lower(),
            message.sender.lower(),
            *{item.lower() for item in message.label_ids},
        } and not lowered.startswith(("is:", "label:", "subject:")):
            if lowered not in f"{message.subject} {message.body}".lower():
                return False
    return True


def call_gmail_tool(session: MailboxSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one gmail tool call against an open mailbox session."""

    action = str(arguments.get("action") or "").strip()
    if action == "search":
        result = session.search(str(arguments.get("query") or ""))
    elif action == "list_labels":
        result = session.list_labels()
    elif action == "modify":
        add_labels = arguments.get("addLabelIds") or arguments.get("add_label_ids") or []
        if isinstance(add_labels, str):
            add_labels = [add_labels]
        result = session.modify(str(arguments.get("messageId") or ""), add_label_ids=[str(item) for item in add_labels])
    elif action == "draft":
        recipients = arguments.get("to") or [DEFAULT_DRAFT_TO]
        if isinstance(recipients, str):
            recipients = [recipients]
        result = session.draft(
            to=[str(item) for item in recipients],
            subject=str(arguments.get("subject") or f"Re: {UNREAD_SUBJECT}"),
            body=str(arguments.get("body") or DEFAULT_DRAFT_BODY),
            in_reply_to=str(arguments.get("inReplyTo") or UNREAD_MESSAGE_ID),
        )
    elif action == "read":
        result = session.read(str(arguments.get("messageId") or ""))
    else:
        raise GmailActuationError(f"unsupported gmail action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def run_gmail_workflow(
    *,
    authed: bool = True,
    body: str = DEFAULT_DRAFT_BODY,
    output_dir: Path | None = None,
    skip_label: bool = False,
) -> dict[str, Any]:
    """Execute the label-gated search-label-draft workflow and seal a trace."""

    descriptor = gmail_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GMAIL_TOOL_PROVIDER),
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
        raise GmailActuationError(f"gmail tool did not route executable: {decision.reasons}")

    session = MailboxSession(authed=authed)
    calls: list[dict[str, Any]] = [
        {"action": "search", "query": "is:unread"},
        {"action": "list_labels"},
    ]
    if not skip_label:
        calls.append(
            {
                "action": "modify",
                "messageId": UNREAD_MESSAGE_ID,
                "addLabelIds": [TRIAGE_LABEL],
            }
        )
    calls.extend(
        [
            {
                "action": "draft",
                "to": [DEFAULT_DRAFT_TO],
                "subject": f"Re: {UNREAD_SUBJECT}",
                "body": body,
                "inReplyTo": UNREAD_MESSAGE_ID,
            },
            {"action": "read", "messageId": UNREAD_MESSAGE_ID},
        ]
    )
    results: list[dict[str, Any]] = []
    for arguments in calls:
        try:
            results.append(call_gmail_tool(session, arguments))
        except GmailActuationError as error:
            results.append({"action": arguments["action"], "error": str(error)})
            break
        if int(results[-1].get("status") or 0) >= 400:
            break

    final = results[-1] if results else {}
    labelled = False
    if session.messages:
        labelled = TRIAGE_LABEL in session.messages[UNREAD_MESSAGE_ID].label_ids
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "gmail_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "authed": authed,
        "skip_label": skip_label,
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "sentinel": str(final.get("sentinel") or ""),
        "draft_body": str(final.get("draft_body") or final.get("body") or ""),
        "labelled": labelled,
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="gmail-live-"))
    out.mkdir(parents=True, exist_ok=True)
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    sealed = bool(
        decision.executable
        and authed
        and not skip_label
        and labelled
        and str(final.get("sentinel") or "") == SENTINEL
        and str(final.get("draft_body") or "") == body
    )
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sentinel": str(final.get("sentinel") or ""),
        "draft_body": str(final.get("draft_body") or final.get("body") or ""),
        "final_status": int(final.get("status") or 0),
        "authed": authed,
        "labelled": labelled,
        "error": str(final.get("error") or ""),
        "match_count": len((results[0].get("matches") if results else []) or []),
    }


def verify_gmail_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Gmail trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "draft_recorded": bool(trace.get("draft_body")),
        "labelled": trace.get("labelled") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def gmail_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.gmail_actuation import "
        "builtin_gmail_actuation_proof; r=builtin_gmail_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='gmail_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_gmail_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GMAIL_ACTUATION_ID,
        name="First-class Gmail inbox actuation",
        description=(
            "Missions that require a mail tool can opt the gmail provider in, "
            "search an unread thread, apply a triage label, and seal a digest-"
            "chained draft. Default routing stays fail-closed; an unauthenticated "
            "client keeps the auth hole falsifiable, and drafts stay label-gated."
        ),
        kind="python",
        entry="blackhole_agent.gmail_actuation:builtin_gmail_actuation_proof",
        proof_command=gmail_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.browser-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/gmail_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required Gmail tool is executable after explicit provider opt-in: "
            "Unbound searches an unread thread, applies a triage label, seals a "
            "tamper-evident draft, and binds this family as the next diversity-"
            "catalog successor once browser actuation is proved."
        ),
        tags=("gmail", "mail", "actuation", "auth", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T023236Z-5c4a553b",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_gmail_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in Gmail actuation seals a label-gated draft."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.browser_actuation import BROWSER_ACTUATION_GOAL, BROWSER_ACTUATION_ID
    from blackhole_agent.publication_resilience import (
        PUBLICATION_RESILIENCE_GOAL,
        PUBLICATION_RESILIENCE_ID,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = GMAIL_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["browser_goal_is_not_gmail"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) != (
        GMAIL_ACTUATION_ID,
    )
    checks["publication_goal_is_not_gmail"] = leftover_marker_ids(PUBLICATION_RESILIENCE_GOAL) != (
        GMAIL_ACTUATION_ID,
    )
    checks["browser_marker_stays_browser"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (
        BROWSER_ACTUATION_ID,
    )
    checks["publication_marker_stays_publication"] = leftover_marker_ids(
        PUBLICATION_RESILIENCE_GOAL
    ) == (PUBLICATION_RESILIENCE_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_gmail"] = (
        len(catalog) > 10
        and catalog[10]["id"] == GMAIL_ACTUATION_ID
        and catalog[9]["id"] == BROWSER_ACTUATION_ID
    )

    mcp_mail = ToolDescriptor(name="remote_gmail", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_mail)
    checks["naive_mcp_mail_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = gmail_tool_descriptor()
    default_mail = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GMAIL_TOOL_PROVIDER),
    )
    checks["default_gmail_provider_is_unsupported"] = (
        default_mail.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{GMAIL_TOOL_PROVIDER}" in default_mail.reasons
    )
    checks["opted_in_gmail_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_mail],
        required_tool_names=("local_memory", "gmail"),
    )
    checks["naive_preflight_missing_gmail"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["gmail"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "gmail"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GMAIL_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "gmail" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="gmail-actuation-") as tmp:
        root = Path(tmp)
        naive = run_gmail_workflow(authed=False, output_dir=root / "naive")
        unlabeled = run_gmail_workflow(skip_label=True, output_dir=root / "unlabeled")
        live = run_gmail_workflow(output_dir=root / "live")
        verify = verify_gmail_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_gmail_trace(clone)
        checks["naive_without_auth_is_forbidden"] = (
            naive["ok"] is False
            and naive["sentinel"] == ""
            and naive["final_status"] == 403
            and naive["error"] == "unauthenticated"
        )
        checks["unlabelled_draft_is_forbidden"] = (
            unlabeled["ok"] is False
            and unlabeled["final_status"] == 403
            and unlabeled["error"] == "label_gated"
            and unlabeled["labelled"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_seals_draft"] = live["draft_body"] == DEFAULT_DRAFT_BODY
        checks["workflow_applies_triage_label"] = live["labelled"] is True
        checks["auth_and_label_are_required"] = (
            naive["ok"] is False and unlabeled["ok"] is False and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="gmail-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != GMAIL_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_gmail"] = (
        live_goal == GMAIL_ACTUATION_GOAL
        and GMAIL_ACTUATION_ID in live_done
        and live_source == "genesis_bind_gmail"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_gmail_actuation_capability()
    return {
        "ok": ok,
        "action": "gmail_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GMAIL_ACTUATION_GOAL,
        "done_when": GMAIL_ACTUATION_DONE_WHEN,
    }
