"""Tool descriptor metadata helpers for local agent routing."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass, replace
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


def canonical_tool_schema(value: Mapping[str, Any] | None) -> str:
    """Return a stable representation for JSON-schema-shaped tool metadata."""

    if value is None:
        return "null"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class ToolDescriptor:
    """A local tool declaration with all fields needed for compatibility checks."""

    name: str
    description: str = ""
    parameters: Mapping[str, Any] | None = None
    provider: str = "local"
    session_id: str | None = None
    tool_type: str | None = None
    callable_path: str | None = None
    policy_name: str | None = None
    risk_flags: tuple[str, ...] = ()

    def compatibility_key(self) -> str:
        """Key cache entries by every field that changes call compatibility."""

        payload = {
            "callable_path": self.callable_path,
            "description": self.description,
            "name": self.name,
            "parameters": self.parameters,
            "policy_name": self.policy_name,
            "provider": self.provider,
            "risk_flags": self.risk_flags,
            "session_id": self.session_id,
            "tool_type": self.tool_type,
        }
        return canonical_tool_schema(payload)

    @property
    def policy_identity(self) -> str:
        """Declared tool identity used by policy gates."""

        return self.policy_name or self.name

    def for_policy_evaluation(self) -> ToolDescriptor:
        """Return the descriptor identity a policy evaluator should match."""

        if self.policy_name is None or self.policy_name == self.name:
            return self
        return replace(self, name=self.policy_name)

    def to_call_metadata(self) -> dict[str, Any]:
        """Emit model-facing metadata without dropping the parameter schema."""

        metadata: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
        }
        if self.session_id is not None:
            metadata["session_id"] = self.session_id
        if self.tool_type is not None:
            metadata["type"] = self.tool_type
        if self.callable_path is not None:
            metadata["callable"] = self.callable_path
        if self.policy_name is not None and self.policy_name != self.name:
            metadata["policy_name"] = self.policy_name
        if self.parameters is not None:
            metadata["parameters"] = dict(self.parameters)
        return metadata


EXECUTABLE_TOOL_ROUTE = "executable"
DENIED_TOOL_ROUTE = "denied"
REVIEW_ONLY_TOOL_ROUTE = "review_only"
UNSUPPORTED_TOOL_ROUTE = "unsupported"
DEFAULT_EXECUTABLE_TOOL_PROVIDERS = ("local", "function")
DEFAULT_EXECUTABLE_TOOL_TYPES = (None, "function")
HEADLESS_FUNCTION_CALL_EVENT_TYPES = frozenset({"function_call", "tool_call"})
TOOL_REVIEW_RISK_FLAGS = frozenset(
    {
        "abuse",
        "offensive-behavior",
        "privacy-leakage",
        "unauthorized-access",
    }
)


@dataclass(frozen=True)
class ToolRouteDecision:
    """Controller-owned decision for exposing or withholding a tool descriptor."""

    descriptor: ToolDescriptor
    route: str
    reasons: tuple[str, ...] = ()

    @property
    def executable(self) -> bool:
        return self.route == EXECUTABLE_TOOL_ROUTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.descriptor.name,
            **(
                {"policy_name": self.descriptor.policy_identity}
                if self.descriptor.policy_identity != self.descriptor.name
                else {}
            ),
            "provider": self.descriptor.provider,
            "route": self.route,
            "reasons": list(self.reasons),
            "risk_flags": list(self.descriptor.risk_flags),
            "type": self.descriptor.tool_type,
        }


@dataclass(frozen=True)
class ToolCallPolicyResult:
    """Result returned by connector-native policy evaluation for a tool call route."""

    allowed: bool
    reason: str = ""
    review_required: bool = False


ToolCallPolicyEvaluator = Callable[[ToolDescriptor], bool | ToolCallPolicyResult]


def route_tool_descriptor(
    descriptor: ToolDescriptor,
    *,
    executable_providers: Sequence[str] = DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    executable_tool_types: Sequence[str | None] = DEFAULT_EXECUTABLE_TOOL_TYPES,
    review_risk_flags: frozenset[str] = TOOL_REVIEW_RISK_FLAGS,
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> ToolRouteDecision:
    """Classify a tool descriptor before it can enter the executable registry."""

    reasons: list[str] = []
    risky_flags = sorted(set(descriptor.risk_flags) & set(review_risk_flags))
    if risky_flags:
        return ToolRouteDecision(
            descriptor=descriptor,
            route=REVIEW_ONLY_TOOL_ROUTE,
            reasons=tuple(f"review_only_risk:{flag}" for flag in risky_flags),
        )

    policy_route, policy_reason = evaluate_tool_call_policy_route(descriptor, tool_call_policy_evaluator)
    if policy_route is not None:
        return ToolRouteDecision(
            descriptor=descriptor,
            route=policy_route,
            reasons=(policy_reason,),
        )

    if descriptor.provider not in set(executable_providers):
        reasons.append(f"unsupported_provider:{descriptor.provider}")
    if descriptor.tool_type not in set(executable_tool_types):
        reasons.append(f"unsupported_tool_type:{descriptor.tool_type}")
    if descriptor.provider == "function" and descriptor.tool_type == "function" and not descriptor.callable_path:
        reasons.append("missing_callable:function")

    if reasons:
        return ToolRouteDecision(descriptor=descriptor, route=UNSUPPORTED_TOOL_ROUTE, reasons=tuple(reasons))
    return ToolRouteDecision(descriptor=descriptor, route=EXECUTABLE_TOOL_ROUTE)


def evaluate_tool_call_policy(
    descriptor: ToolDescriptor,
    evaluator: ToolCallPolicyEvaluator | None,
) -> str | None:
    """Return a fail-closed denial reason when a connector policy gate does not allow a tool."""

    route, reason = evaluate_tool_call_policy_route(descriptor, evaluator)
    if route == DENIED_TOOL_ROUTE:
        return reason
    return None


def evaluate_tool_call_policy_route(
    descriptor: ToolDescriptor,
    evaluator: ToolCallPolicyEvaluator | None,
) -> tuple[str | None, str]:
    """Return a fail-closed route and reason for connector policy evaluation."""

    if evaluator is None:
        return None, ""
    try:
        result = evaluator(descriptor.for_policy_evaluation())
    except TimeoutError:
        return DENIED_TOOL_ROUTE, "policy_evaluation_timeout"
    except Exception as error:
        return DENIED_TOOL_ROUTE, f"policy_evaluation_error:{type(error).__name__}"

    if isinstance(result, ToolCallPolicyResult):
        if not isinstance(result.allowed, bool):
            return DENIED_TOOL_ROUTE, "policy_evaluation_malformed:allowed"
        if not isinstance(result.review_required, bool):
            return DENIED_TOOL_ROUTE, "policy_evaluation_malformed:review_required"
        if not result.allowed:
            return DENIED_TOOL_ROUTE, f"policy_denied:{result.reason or 'unspecified'}"
        if result.review_required:
            return REVIEW_ONLY_TOOL_ROUTE, f"policy_review_required:{result.reason or 'unspecified'}"
        return None, ""
    if result is True:
        return None, ""
    if result is False:
        return DENIED_TOOL_ROUTE, "policy_denied:unspecified"
    return DENIED_TOOL_ROUTE, f"policy_evaluation_malformed:{type(result).__name__}"


def route_tool_descriptors(
    descriptors: Sequence[ToolDescriptor],
    *,
    executable_providers: Sequence[str] = DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    executable_tool_types: Sequence[str | None] = DEFAULT_EXECUTABLE_TOOL_TYPES,
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> tuple[ToolRouteDecision, ...]:
    """Return inspectable routing decisions for a batch of descriptors."""

    return tuple(
        route_tool_descriptor(
            descriptor,
            executable_providers=executable_providers,
            executable_tool_types=executable_tool_types,
            tool_call_policy_evaluator=tool_call_policy_evaluator,
        )
        for descriptor in descriptors
    )


def build_tool_routing_preflight(
    descriptors: Sequence[ToolDescriptor],
    *,
    required_tool_names: Sequence[str] = (),
    executable_providers: Sequence[str] = DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    executable_tool_types: Sequence[str | None] = DEFAULT_EXECUTABLE_TOOL_TYPES,
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> dict[str, Any]:
    """Return startup-safe diagnostics for local tool routing capabilities."""

    decisions = route_tool_descriptors(
        descriptors,
        executable_providers=executable_providers,
        executable_tool_types=executable_tool_types,
        tool_call_policy_evaluator=tool_call_policy_evaluator,
    )
    executable_names = sorted(decision.descriptor.name for decision in decisions if decision.executable)
    executable_name_set = set(executable_names)
    required_names = tuple(dict.fromkeys(name for name in required_tool_names if name))
    missing_required = [name for name in required_names if name not in executable_name_set]
    diagnostics = [f"required tool is not executable or is unavailable: {name}" for name in missing_required]
    route_counts: dict[str, int] = {}
    for decision in decisions:
        route_counts[decision.route] = route_counts.get(decision.route, 0) + 1
    return {
        "schema_version": 1,
        "ok": not diagnostics,
        "diagnostics": diagnostics,
        "tool_count": len(decisions),
        "required_tool_names": list(required_names),
        "missing_required_tool_names": missing_required,
        "executable_tool_names": executable_names,
        "route_counts": route_counts,
        "decisions": [decision.to_dict() for decision in decisions],
    }


class ToolCompatibilityCache:
    """Small cache keyed by full tool compatibility descriptors."""

    def __init__(self) -> None:
        self._entries: dict[str, Any] = {}

    def set(self, descriptor: ToolDescriptor, value: Any) -> str:
        key = descriptor.compatibility_key()
        self._entries[key] = value
        return key

    def get(self, descriptor: ToolDescriptor) -> Any:
        return self._entries.get(descriptor.compatibility_key())

    def __len__(self) -> int:
        return len(self._entries)


@dataclass(frozen=True)
class ProviderHarness:
    """Provider or SDK harness candidate with locally checkable capability requirements."""

    name: str
    provider: str
    priority: int = 100
    enabled: bool = True
    required_modules: tuple[str, ...] = ()
    optional_extra_modules: tuple[str, ...] = ()
    required_commands: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    supported_platforms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderHarnessStatus:
    """Discovery result for one provider harness candidate."""

    harness: ProviderHarness
    available: bool
    skip_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "name": self.harness.name,
            "priority": self.harness.priority,
            "provider": self.harness.provider,
            "skip_reasons": list(self.skip_reasons),
        }


@dataclass(frozen=True)
class ProviderHarnessSelection:
    """Deterministic provider harness routing decision with all skipped candidates retained."""

    selected: ProviderHarness | None
    statuses: tuple[ProviderHarnessStatus, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.name if self.selected else None,
            "statuses": [status.to_dict() for status in self.statuses],
        }


def default_provider_harnesses() -> tuple[ProviderHarness, ...]:
    """Return the built-in fallback order for locally supported agent providers.

    The first-class local CLI kernels this repository actually runs (Codex,
    Grok, Kimi — see ``blackhole_agent.kernels``) outrank third-party SDK
    shims; the single-file function agent remains the dependency-free
    fallback.
    """

    return (
        ProviderHarness(
            name="codex-cli",
            provider="codex",
            priority=10,
            required_commands=("codex",),
        ),
        ProviderHarness(
            name="grok-cli",
            provider="grok",
            priority=12,
            required_commands=("grok",),
        ),
        ProviderHarness(
            name="kimi-cli",
            provider="kimi",
            priority=14,
            required_commands=("kimi",),
        ),
        ProviderHarness(
            name="copilot-sdk",
            provider="copilot",
            priority=20,
            optional_extra_modules=("github_copilot",),
        ),
        ProviderHarness(
            name="cursor-sdk",
            provider="cursor",
            priority=30,
            optional_extra_modules=("cursor_agent",),
        ),
        ProviderHarness(
            name="single-file-function-agent",
            provider="function",
            priority=90,
        ),
    )


def select_provider_harness(
    harnesses: Sequence[ProviderHarness] | None = None,
    *,
    installed_modules: set[str] | None = None,
    available_commands: set[str] | None = None,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> ProviderHarnessSelection:
    """Select the first available provider harness and retain deterministic skip diagnostics."""

    statuses = discover_provider_harnesses(
        harnesses or default_provider_harnesses(),
        installed_modules=installed_modules,
        available_commands=available_commands,
        environ=environ,
        platform=platform,
    )
    selected = next((status.harness for status in statuses if status.available), None)
    return ProviderHarnessSelection(selected=selected, statuses=tuple(statuses))


def discover_provider_harnesses(
    harnesses: Sequence[ProviderHarness],
    *,
    installed_modules: set[str] | None = None,
    available_commands: set[str] | None = None,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> tuple[ProviderHarnessStatus, ...]:
    """Discover provider harness availability without importing optional SDKs."""

    env = os.environ if environ is None else environ
    current_platform = sys.platform if platform is None else platform
    ordered = sorted(harnesses, key=lambda harness: (harness.priority, harness.name))
    return tuple(
        _provider_harness_status(
            harness,
            installed_modules=installed_modules,
            available_commands=available_commands,
            environ=env,
            platform=current_platform,
        )
        for harness in ordered
    )


def _provider_harness_status(
    harness: ProviderHarness,
    *,
    installed_modules: set[str] | None,
    available_commands: set[str] | None,
    environ: Mapping[str, str],
    platform: str,
) -> ProviderHarnessStatus:
    reasons: list[str] = []
    if not harness.enabled:
        reasons.append("disabled_runner")
    if harness.supported_platforms and platform not in harness.supported_platforms:
        reasons.append(f"unsupported_platform:{platform}")
    for module in harness.required_modules:
        if not _module_available(module, installed_modules):
            reasons.append(f"missing_dependency:{module}")
    for module in harness.optional_extra_modules:
        if not _module_available(module, installed_modules):
            reasons.append(f"missing_optional_extra:{module}")
    for command in harness.required_commands:
        if not _command_available(command, available_commands):
            reasons.append(f"missing_dependency:{command}")
    for name in harness.required_env:
        if not str(environ.get(name) or "").strip():
            reasons.append(f"missing_env:{name}")
    return ProviderHarnessStatus(harness=harness, available=not reasons, skip_reasons=tuple(reasons))


def _module_available(module: str, installed_modules: set[str] | None) -> bool:
    if installed_modules is not None:
        return module in installed_modules
    return find_spec(module) is not None


def _command_available(command: str, available_commands: set[str] | None) -> bool:
    if available_commands is not None:
        return command in available_commands
    return shutil.which(command) is not None


def local_memory_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the local first-party memory route."""

    return ToolDescriptor(
        name="local_memory",
        description=(
            "Store and retrieve non-secret local agent memory in an isolated namespace. "
            "Writes are rejected when they look like secrets, credentials, private keys, or personal data."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["write", "read", "list", "delete"]},
                "namespace": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$",
                    "default": "agent",
                },
                "key": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
                "value": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
                    "default": [],
                },
                "tag": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider="local",
        session_id=session_id,
    )


BROWSER_TOOL_PROVIDER = "browser"


def browser_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party browser actuation route.

    Provider ``browser`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live web session silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="browser",
        description=(
            "Drive a first-class browser session: navigate, click, type, submit, "
            "and read a local or opted-in page. Cookie-gated workflows stay "
            "sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "click", "type", "submit", "read"],
                },
                "url": {"type": "string"},
                "text": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BROWSER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


GMAIL_TOOL_PROVIDER = "gmail"


def gmail_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party Gmail inbox actuation route.

    Provider ``gmail`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live mailbox silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="gmail",
        description=(
            "Drive a first-class Gmail session: search, list labels, modify "
            "labels, draft, and read an opted-in mailbox. Label-gated drafts "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "list_labels", "modify", "draft", "read"],
                },
                "query": {"type": "string"},
                "messageId": {"type": "string"},
                "addLabelIds": {"type": "array", "items": {"type": "string"}},
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "inReplyTo": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GMAIL_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


GODOT_TOOL_PROVIDER = "godot"


def godot_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party Godot scene actuation route.

    Provider ``godot`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live engine session silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="godot",
        description=(
            "Drive a first-class Godot session: list projects, inspect a "
            "project.godot, create a scene, add a node, save, run, and read "
            "debug output. Project-gated play-checks stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list_projects",
                        "get_project_info",
                        "create_scene",
                        "add_node",
                        "save_scene",
                        "run_project",
                        "get_debug_output",
                        "stop_project",
                    ],
                },
                "directory": {"type": "string"},
                "scenePath": {"type": "string"},
                "scene": {"type": "string"},
                "rootNodeType": {"type": "string"},
                "parentNodePath": {"type": "string"},
                "nodeType": {"type": "string"},
                "nodeName": {"type": "string"},
                "properties": {"type": "object"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GODOT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


GITHUB_TOOL_PROVIDER = "github"


def github_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party GitHub issue/PR actuation route.

    Provider ``github`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live repository silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="github",
        description=(
            "Drive a first-class GitHub session: search issues, list labels, "
            "add a triage label, open a pull request, and read the sealed PR. "
            "Issue-gated pull requests stay sealed as digest-chained actuation "
            "traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "list_labels", "add_label", "create_pr", "read_pr"],
                },
                "query": {"type": "string"},
                "issueNumber": {"type": "integer"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "head": {"type": "string"},
                "base": {"type": "string"},
                "closes": {"type": "integer"},
                "prNumber": {"type": "integer"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GITHUB_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


SQLITE_TOOL_PROVIDER = "sqlite"


def sqlite_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party SQLite schema-gated storage route.

    Provider ``sqlite`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live database silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sqlite",
        description=(
            "Drive a first-class SQLite session: open a database file, apply a "
            "schema migration, insert inside a transaction, commit or roll back, "
            "and query the sealed beacon. Schema-gated writes stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open", "migrate", "insert", "commit", "rollback", "query", "close"],
                },
                "token": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SQLITE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


WEBHOOK_TOOL_PROVIDER = "webhook"


def webhook_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party HMAC-gated inbound webhook route.

    Provider ``webhook`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="webhook",
        description=(
            "Drive a first-class webhook session: bind a loopback HTTP listener, "
            "receive an inbound POST, verify X-Hub-Signature-256, ack the sealed "
            "payload, and read it back. HMAC-gated deliveries stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "receive", "verify", "ack", "read", "close"],
                },
                "token": {"type": "string"},
                "signed": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBHOOK_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


SMTP_TOOL_PROVIDER = "smtp"


def smtp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party envelope-gated outbound SMTP route.

    Provider ``smtp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="smtp",
        description=(
            "Drive a first-class SMTP session: bind a loopback SMTP listener, "
            "AUTH PLAIN, land a MAIL FROM / RCPT TO / DATA transaction, and "
            "read the sealed mailbox. Envelope-gated deliveries stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "send", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SMTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


IMAP_TOOL_PROVIDER = "imap"


def imap_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party UID/IDLE-gated inbound IMAP route.

    Provider ``imap`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="imap",
        description=(
            "Drive a first-class IMAP session: bind a loopback IMAP4rev1 listener, "
            "AUTHENTICATE PLAIN, SELECT INBOX, IDLE until EXISTS, UID FETCH the "
            "newly arrived message, and read the sealed inbox. UID-gated inbound "
            "mail stays sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "fetch", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "idle": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IMAP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


REDIS_TOOL_PROVIDER = "redis"
MQTT_TOOL_PROVIDER = "mqtt"
DNS_TOOL_PROVIDER = "dns"
LDAP_TOOL_PROVIDER = "ldap"
POSTGRES_TOOL_PROVIDER = "postgres"
S3_TOOL_PROVIDER = "s3"
WATCH_TOOL_PROVIDER = "watch"
WEBSOCKET_TOOL_PROVIDER = "websocket"
SSH_TOOL_PROVIDER = "ssh"
GRPC_TOOL_PROVIDER = "grpc"
AMQP_TOOL_PROVIDER = "amqp"
FTP_TOOL_PROVIDER = "ftp"
TFTP_TOOL_PROVIDER = "tftp"
SNMP_TOOL_PROVIDER = "snmp"
SYSLOG_TOOL_PROVIDER = "syslog"
NTP_TOOL_PROVIDER = "ntp"
RADIUS_TOOL_PROVIDER = "radius"
DHCP_TOOL_PROVIDER = "dhcp"
IKE_TOOL_PROVIDER = "ike"
SIP_TOOL_PROVIDER = "sip"
STUN_TOOL_PROVIDER = "stun"
TURN_TOOL_PROVIDER = "turn"
ICE_TOOL_PROVIDER = "ice"
DTLS_TOOL_PROVIDER = "dtls"
SRTP_TOOL_PROVIDER = "srtp"
SCTP_TOOL_PROVIDER = "sctp"
DATACHANNEL_TOOL_PROVIDER = "datachannel"
QUIC_TOOL_PROVIDER = "quic"
HTTP3_TOOL_PROVIDER = "http3"
WEBTRANSPORT_TOOL_PROVIDER = "webtransport"
DATAGRAM_TOOL_PROVIDER = "datagram"
MASQUE_TOOL_PROVIDER = "masque"
CONNECTIP_TOOL_PROVIDER = "connectip"
OHTTP_TOOL_PROVIDER = "ohttp"
OHSVCB_TOOL_PROVIDER = "ohsvcb"
HTTPSIG_TOOL_PROVIDER = "httpsig"
DIGESTFIELDS_TOOL_PROVIDER = "digestfields"
BHTTP_TOOL_PROVIDER = "bhttp"
HTTP11_TOOL_PROVIDER = "http11"
HTTP2_TOOL_PROVIDER = "http2"
HTTPCACHE_TOOL_PROVIDER = "httpcache"
HTTPSMANTICS_TOOL_PROVIDER = "httpsemantics"
STRUCTUREDFIELDS_TOOL_PROVIDER = "structuredfields"
CLIENTHINTS_TOOL_PROVIDER = "clienthints"
EARLYHINTS_TOOL_PROVIDER = "earlyhints"
ENCRYPTEDCONTENT_TOOL_PROVIDER = "encryptedcontent"
ALTSVC_TOOL_PROVIDER = "altsvc"
HSTS_TOOL_PROVIDER = "hsts"
HPKP_TOOL_PROVIDER = "hpkp"
EXPECTCT_TOOL_PROVIDER = "expectct"
XFO_TOOL_PROVIDER = "xfo"
WEBORIGIN_TOOL_PROVIDER = "weborigin"
HTTPCOOKIE_TOOL_PROVIDER = "httpcookie"
CONTENTDISPOSITION_TOOL_PROVIDER = "contentdisposition"
WEBLINKING_TOOL_PROVIDER = "weblinking"
EXTVALUE_TOOL_PROVIDER = "extvalue"
STALECONTENT_TOOL_PROVIDER = "stalecontent"
HTTPPATCH_TOOL_PROVIDER = "httppatch"
WELLKNOWN_TOOL_PROVIDER = "wellknown"
WEBDAV_TOOL_PROVIDER = "webdav"
SPNEGO_TOOL_PROVIDER = "spnego"
HTTPTLS_TOOL_PROVIDER = "httptls"
HTTPAUTH_TOOL_PROVIDER = "httpauth"
TCN_TOOL_PROVIDER = "tcn"
HITMETER_TOOL_PROVIDER = "hitmeter"
ICP_TOOL_PROVIDER = "icp"
HTTPVER_TOOL_PROVIDER = "httpver"
HTTPSTATE_TOOL_PROVIDER = "httpstate"
DIGESTAUTH_TOOL_PROVIDER = "digestauth"
HTTP10_TOOL_PROVIDER = "http10"
URL_TOOL_PROVIDER = "url"
URI_TOOL_PROVIDER = "uri"
MIME_TOOL_PROVIDER = "mime"
GOPHER_TOOL_PROVIDER = "gopher"
FINGER_TOOL_PROVIDER = "finger"
LPD_TOOL_PROVIDER = "lpd"
NNTP_TOOL_PROVIDER = "nntp"
TELNET_TOOL_PROVIDER = "telnet"
TCP_TOOL_PROVIDER = "tcp"
UDP_TOOL_PROVIDER = "udp"
ICMP_TOOL_PROVIDER = "icmp"
IP_TOOL_PROVIDER = "ip"
ARP_TOOL_PROVIDER = "arp"
RARP_TOOL_PROVIDER = "rarp"
IGMP_TOOL_PROVIDER = "igmp"
MLD_TOOL_PROVIDER = "mld"
NDP_TOOL_PROVIDER = "ndp"
SLAAC_TOOL_PROVIDER = "slaac"
TEMPADDR_TOOL_PROVIDER = "tempaddr"
OPAQUEIID_TOOL_PROVIDER = "opaqueiid"
CGA_TOOL_PROVIDER = "cga"
SEND_TOOL_PROVIDER = "send"
ULA_TOOL_PROVIDER = "ula"
IPV6ADDR_TOOL_PROVIDER = "ipv6addr"
IPV6SCOPE_TOOL_PROVIDER = "ipv6scope"
ADDRSELECT_TOOL_PROVIDER = "addrselect"
ADDRPOLICY_TOOL_PROVIDER = "addrpolicy"
FIRSTHOP_TOOL_PROVIDER = "firsthop"
RDNSS_TOOL_PROVIDER = "rdnss"
PREF64_TOOL_PROVIDER = "pref64"
NAT64_TOOL_PROVIDER = "nat64"
DNS64_TOOL_PROVIDER = "dns64"
XLAT_TOOL_PROVIDER = "xlat"
DISC_TOOL_PROVIDER = "disc"
DSLITE_TOOL_PROVIDER = "dslite"
LW4O6_TOOL_PROVIDER = "lw4o6"
MAPE_TOOL_PROVIDER = "mape"
MAPT_TOOL_PROVIDER = "mapt"
S46_TOOL_PROVIDER = "s46"
UCPE_TOOL_PROVIDER = "ucpe"
M46_TOOL_PROVIDER = "m46"
PREFIX64_TOOL_PROVIDER = "prefix64"
SIIT_TOOL_PROVIDER = "siit"
EAM_TOOL_PROVIDER = "eam"
SIITDC_TOOL_PROVIDER = "siitdc"
SIITDTM_TOOL_PROVIDER = "siitdtm"
V4EMBED_TOOL_PROVIDER = "v4embed"
LUPREFIX_TOOL_PROVIDER = "luprefix"
SIXRD_TOOL_PROVIDER = "sixrd"
SIXTO4_TOOL_PROVIDER = "sixto4"
TEREDO_TOOL_PROVIDER = "teredo"
ISATAP_TOOL_PROVIDER = "isatap"
SIXOVER4_TOOL_PROVIDER = "sixover4"
SIXIN4_TOOL_PROVIDER = "sixin4"
TSP_TOOL_PROVIDER = "tsp"
L2TP_TOOL_PROVIDER = "l2tp"
MESH_TOOL_PROVIDER = "mesh"
ENCAP_TOOL_PROVIDER = "encap"
MPBGP_TOOL_PROVIDER = "mpbgp"
BGP4_TOOL_PROVIDER = "bgp4"
RTREFRESH_TOOL_PROVIDER = "rtrefresh"
BGPCOMM_TOOL_PROVIDER = "bgpcomm"
EXTCOMM_TOOL_PROVIDER = "extcomm"
LARGECOMM_TOOL_PROVIDER = "largecomm"
BGPSEC_TOOL_PROVIDER = "bgpsec"
RTR_TOOL_PROVIDER = "rtr"
EBGP_TOOL_PROVIDER = "ebgp"
EVPN_TOOL_PROVIDER = "evpn"
ETREE_TOOL_PROVIDER = "etree"
NVO_TOOL_PROVIDER = "nvo"
DFE_TOOL_PROVIDER = "dfe"
IRB_TOOL_PROVIDER = "irb"
IPPFX_TOOL_PROVIDER = "ippfx"
PROXYND_TOOL_PROVIDER = "proxynd"
IMLPROXY_TOOL_PROVIDER = "imlproxy"
EVPNBUM_TOOL_PROVIDER = "evpnbum"
FXC_TOOL_PROVIDER = "fxc"
DFREC_TOOL_PROVIDER = "dfrec"
MSRED_TOOL_PROVIDER = "msred"
P2MPIR_TOOL_PROVIDER = "p2mpir"
OIR_TOOL_PROVIDER = "oir"
IESI_TOOL_PROVIDER = "iesi"
PBB_TOOL_PROVIDER = "pbb"
MACIP_TOOL_PROVIDER = "macip"
EVPNREQ_TOOL_PROVIDER = "evpnreq"
VPLS_TOOL_PROVIDER = "vpls"
LDPSIG_TOOL_PROVIDER = "ldpsig"
PWLDP_TOOL_PROVIDER = "pwldp"
PWE3_TOOL_PROVIDER = "pwe3"
PWREQ_TOOL_PROVIDER = "pwreq"
MPLSARCH_TOOL_PROVIDER = "mplsarch"
MPLSLSE_TOOL_PROVIDER = "mplslse"
RSVPTE_TOOL_PROVIDER = "rsvpte"
GMPLS_TOOL_PROVIDER = "gmpls"
LMP_TOOL_PROVIDER = "lmp"
LSPHIER_TOOL_PROVIDER = "lsphier"
GUNI_TOOL_PROVIDER = "guni"
LWDM_TOOL_PROVIDER = "lwdm"
OTN_TOOL_PROVIDER = "otn"
ASON_TOOL_PROVIDER = "ason"
GREC_TOOL_PROVIDER = "grec"
E2EREC_TOOL_PROVIDER = "e2erec"
SEGREC_TOOL_PROVIDER = "segrec"
EXROUTE_TOOL_PROVIDER = "exroute"
P2MPTE_TOOL_PROVIDER = "p2mpte"
CRANKBACK_TOOL_PROVIDER = "crankback"
LSPSTITCH_TOOL_PROVIDER = "lspstitch"
INTERAS_TOOL_PROVIDER = "interas"
PERDOM_TOOL_PROVIDER = "perdom"
PCEP_TOOL_PROVIDER = "pcep"
BRPC_TOOL_PROVIDER = "brpc"
DSCT_TOOL_PROVIDER = "dsct"
PATHKEY_TOOL_PROVIDER = "pathkey"
PCEXCL_TOOL_PROVIDER = "pcexcl"
OBJFUN_TOOL_PROVIDER = "objfun"
GCO_TOOL_PROVIDER = "gco"
ILPCE_TOOL_PROVIDER = "ilpce"
PCEMON_TOOL_PROVIDER = "pcemon"
PCEPMP_TOOL_PROVIDER = "pcepmp"
WSON_TOOL_PROVIDER = "wson"
LSC_TOOL_PROVIDER = "lsc"
ASBW_TOOL_PROVIDER = "asbw"
SMP_TOOL_PROVIDER = "smp"
FMOAM_TOOL_PROVIDER = "fmoam"
PCV_TOOL_PROVIDER = "pcv"
LILB_TOOL_PROVIDER = "lilb"
PWST_TOOL_PROVIDER = "pwst"
MLDP_TOOL_PROVIDER = "mldp"


def redis_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party BLPOP-gated Redis work-queue route.

    Provider ``redis`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="redis",
        description=(
            "Drive a first-class Redis session: bind a loopback RESP listener, "
            "AUTH with requirepass, SELECT a logical database, BLPOP a newly "
            "RPUSH'd job, and read the sealed queue. BLPOP-gated work stays "
            "sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "pop", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "blpop": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=REDIS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mqtt_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party retained-topic MQTT fanout route.

    Provider ``mqtt`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mqtt",
        description=(
            "Drive a first-class MQTT session: bind a loopback MQTT 3.1.1 "
            "listener, CONNECT with a password, PUBLISH a retained topic, "
            "SUBSCRIBE a wildcard filter after the publisher has disconnected, "
            "and read the sealed fanout. Retained-topic deliveries stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "receive", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "subscribe": {"type": "boolean"},
                "retain": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MQTT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dns_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party TSIG-gated DNS apex-record route.

    Provider ``dns`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live nameserver silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dns",
        description=(
            "Drive a first-class DNS session: bind a loopback DNS/UDP "
            "nameserver, UPDATE an apex TXT with HMAC-SHA256 TSIG, QUERY the "
            "record, independently re-QUERY from a fresh socket, and read the "
            "sealed zone. TSIG-gated apex records stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "update": {"type": "boolean"},
                "query": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DNS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ldap_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party BIND/ADD/SEARCH LDAP directory route.

    Provider ``ldap`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live directory silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ldap",
        description=(
            "Drive a first-class LDAP session: bind a loopback LDAP v3 "
            "directory, simple BIND as the directory manager, ADD a "
            "distinguished-name entry, SEARCH it with an equality filter, "
            "independently re-SEARCH from a fresh connection, and read the "
            "sealed DIT. BIND-gated identity entries stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "add": {"type": "boolean"},
                "search": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LDAP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def postgres_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party Startup/Password/SimpleQuery PostgreSQL route.

    Provider ``postgres`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live relational-wire listener silently executable — a caller must opt
    the provider in.
    """

    return ToolDescriptor(
        name="postgres",
        description=(
            "Drive a first-class PostgreSQL session: bind a loopback v3 "
            "frontend/backend listener, send a StartupMessage, cleartext "
            "Password, INSERT a beacon row, SimpleQuery a RowDescription/"
            "DataRow, independently re-Query from a fresh connection, and "
            "read the sealed result. Password-gated relational rows stay "
            "sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "insert": {"type": "boolean"},
                "query": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=POSTGRES_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def s3_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party SigV4 S3 object-store route.

    Provider ``s3`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live object-store listener silently executable — a caller must opt the
    provider in.
    """

    return ToolDescriptor(
        name="s3",
        description=(
            "Drive a first-class S3 session: bind a loopback path-style "
            "listener, sign AWS4-HMAC-SHA256, PutObject a beacon, GetObject "
            "the ETag, ListObjects the bucket, independently re-GET from a "
            "fresh signed request, and read the sealed object. SigV4-gated "
            "object-store payloads stay sealed as digest-chained actuation "
            "traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "put": {"type": "boolean"},
                "get": {"type": "boolean"},
                "list_bucket": {"type": "boolean"},
                "secret": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=S3_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def watch_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party filesystem path-watch mutation route.

    Provider ``watch`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live filesystem observer silently executable — a caller must opt the
    provider in.
    """

    return ToolDescriptor(
        name="watch",
        description=(
            "Drive a first-class path-watch session: bind an on-disk watch "
            "root, subscribe an independent observer, CREATE a beacon, "
            "MODIFY it, CONSUME the mutation events, independently re-hash "
            "the beacon from a fresh file open, and read the sealed change "
            "digest. Path-watch mutations stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "create": {"type": "boolean"},
                "modify": {"type": "boolean"},
                "consume": {"type": "boolean"},
                "secret": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WATCH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def websocket_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6455 websocket upgrade-framing route.

    Provider ``websocket`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live upgrade listener silently executable — a caller must opt the
    provider in.
    """

    return ToolDescriptor(
        name="websocket",
        description=(
            "Drive a first-class RFC 6455 session: bind a loopback websocket "
            "listener, complete a 101 Switching Protocols handshake with "
            "Sec-WebSocket-Accept, mask a client text frame, echo it, answer "
            "a control-frame pong, independently replay the retained payload "
            "on a later connection, and read the sealed frame digest. "
            "Upgrade-gated frames stay sealed as digest-chained actuation "
            "traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "upgrade": {"type": "boolean"},
                "send": {"type": "boolean"},
                "receive": {"type": "boolean"},
                "pong": {"type": "boolean"},
                "mask": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "secret": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBSOCKET_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ssh_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party SSH-2.0 binary-packet exec route.

    Provider ``ssh`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live ssh daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ssh",
        description=(
            "Drive a first-class SSH-2.0 session: bind a loopback daemon, "
            "IDENTIFY SSH-2.0, complete group14 DH KEXINIT, password "
            "USERAUTH, CHANNEL-OPEN a session, EXEC a command, independently "
            "re-EXEC the retained stdout on a later connection, and read the "
            "sealed stdout digest. Password-gated exec output stays sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "identify": {"type": "boolean"},
                "kex": {"type": "boolean"},
                "mac": {"type": "boolean"},
                "channel": {"type": "boolean"},
                "exec": {"type": "boolean"},
                "receive": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SSH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def grpc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party HTTP/2 gRPC length-prefixed RPC route.

    Provider ``grpc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live HTTP/2 listener silently executable — a caller must opt the
    provider in.
    """

    return ToolDescriptor(
        name="grpc",
        description=(
            "Drive a first-class HTTP/2 gRPC session: bind a loopback "
            "listener, complete the connection preface, SETTINGS, HPACK "
            "HEADERS, a length-prefixed protobuf Seal RPC, grpc-status "
            "TRAILERS, independently re-invoke the retained reply on a later "
            "stream, and read the sealed status digest. Metadata-gated RPC "
            "output stays sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "preface": {"type": "boolean"},
                "settings": {"type": "boolean"},
                "headers": {"type": "boolean"},
                "data": {"type": "boolean"},
                "trailers": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "secret": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GRPC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def amqp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party AMQP 0-9-1 work-queue delivery route.

    Provider ``amqp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live broker silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="amqp",
        description=(
            "Drive a first-class AMQP 0-9-1 session: bind a loopback broker, "
            "speak the protocol header, CONNECTION-START/TUNE/OPEN, "
            "CHANNEL-OPEN, QUEUE-DECLARE, BASIC-PUBLISH a content-header plus "
            "body, BASIC-DELIVER a delivery-tag, independently re-consume the "
            "retained last-value on a later connection, and read the sealed "
            "delivery-tag digest. PLAIN-gated work-queue deliveries stay "
            "sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "protocol": {"type": "boolean"},
                "connection": {"type": "boolean"},
                "channel": {"type": "boolean"},
                "declare": {"type": "boolean"},
                "publish": {"type": "boolean"},
                "consume": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=AMQP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ftp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 959 FTP PASV file-transfer route.

    Provider ``ftp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ftp",
        description=(
            "Drive a first-class RFC 959 session: bind a loopback FTP "
            "listener, USER/PASS, TYPE I, PASV, STOR a binary body on a "
            "separate data connection, RETR it, independently RETR the stored "
            "body on a later control session, and read the sealed file "
            "digest. PASV-gated transfers stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "authenticate": {"type": "boolean"},
                "type": {"type": "boolean"},
                "pasv": {"type": "boolean"},
                "store": {"type": "boolean"},
                "retrieve": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "password": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=FTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def tftp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1350 TFTP RRQ/WRQ/DATA/ACK route.

    Provider ``tftp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="tftp",
        description=(
            "Drive a first-class RFC 1350 session: bind a loopback TFTP "
            "listener, WRQ an octet stream, lockstep DATA/ACK opcodes from a "
            "distinct transfer TID, independently RRQ the stored body on a "
            "later client socket, and read the sealed block digest. "
            "TID-gated transfers stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "wrq": {"type": "boolean"},
                "data": {"type": "boolean"},
                "ack": {"type": "boolean"},
                "retrieve": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_transfer_tid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TFTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def snmp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1157 SNMP GET/SET/RESPONSE route.

    Provider ``snmp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live listener silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="snmp",
        description=(
            "Drive a first-class RFC 1157 session: bind a loopback SNMP "
            "listener, SET an OCTET STRING varbind, lockstep GET/RESPONSE "
            "PDUs with a community string, independently GET the stored "
            "varbind on a later client socket, and read the sealed varbind "
            "digest. Community-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "set": {"type": "boolean"},
                "get": {"type": "boolean"},
                "response": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_community": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SNMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def syslog_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5424 syslog PRI/HEADER/SD/MSG route.

    Provider ``syslog`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live collector silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="syslog",
        description=(
            "Drive a first-class RFC 5424 session: bind a loopback syslog "
            "collector, emit PRI, HEADER with a non-NILVALUE hostname, "
            "STRUCTURED-DATA, and MSG, independently replay the stored "
            "datagram on a later client socket, and read the sealed syslog "
            "digest. NILVALUE-gated structured-data stays sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "pri": {"type": "boolean"},
                "header": {"type": "boolean"},
                "structured_data": {"type": "boolean"},
                "msg": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_hostname": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SYSLOG_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ntp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5905 NTP originate/receive/transmit route.

    Provider ``ntp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ntp",
        description=(
            "Drive a first-class RFC 5905 session: bind a loopback NTP "
            "daemon, send a CLIENT packet with an originate timestamp and "
            "keyid MAC, lockstep a SERVER reply that fills receive and "
            "transmit, independently poll the stored origin timestamp on a "
            "later client socket, and read the sealed timestamp digest. "
            "Keyid-gated exchanges stay sealed as digest-chained actuation "
            "traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "client": {"type": "boolean"},
                "server": {"type": "boolean"},
                "originate": {"type": "boolean"},
                "receive": {"type": "boolean"},
                "transmit": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_keyid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=NTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def radius_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2865 RADIUS Access-Request/Access-Accept route.

    Provider ``radius`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="radius",
        description=(
            "Drive a first-class RFC 2865 session: bind a loopback RADIUS "
            "daemon, send an Access-Request with a User-Name attribute and "
            "shared-secret User-Password, lockstep an Access-Accept that "
            "echoes the stored User-Name, independently poll the stored "
            "User-Name on a later client socket, and read the sealed "
            "attribute digest. Secret-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "request": {"type": "boolean"},
                "accept": {"type": "boolean"},
                "username": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_secret": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RADIUS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dhcp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2131 DHCP DISCOVER/OFFER/ACK route.

    Provider ``dhcp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dhcp",
        description=(
            "Drive a first-class RFC 2131 session: bind a loopback DHCP "
            "daemon, send a DISCOVER with a non-zero xid, lockstep an OFFER "
            "then ACK that carries the stored yiaddr lease, independently "
            "poll the stored yiaddr on a later client socket, and read the "
            "sealed lease digest. Xid-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "discover": {"type": "boolean"},
                "offer": {"type": "boolean"},
                "ack": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_xid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DHCP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ike_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7296 IKE SA_INIT/AUTH route.

    Provider ``ike`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ike",
        description=(
            "Drive a first-class RFC 7296 session: bind a loopback IKE "
            "daemon, send IKE_SA_INIT with a non-zero initiator SPI, lockstep "
            "an IKE_AUTH that carries the stored initiator SPI, independently "
            "poll the stored initiator SPI on a later client socket, and read "
            "the sealed spi digest. SPI-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "sa_init": {"type": "boolean"},
                "auth": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_spi": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IKE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def sip_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3261 SIP INVITE/200 route.

    Provider ``sip`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sip",
        description=(
            "Drive a first-class RFC 3261 session: bind a loopback SIP "
            "daemon, send INVITE with a non-empty Call-ID, lockstep a "
            "200 OK that carries the stored dialog Call-ID, independently "
            "poll the stored dialog Call-ID on a later client socket, and read "
            "the sealed callid digest. Call-ID-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "invite": {"type": "boolean"},
                "ok": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_callid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def stun_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5389 STUN Binding Request/Success route.

    Provider ``stun`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live daemon silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="stun",
        description=(
            "Drive a first-class RFC 5389 session: bind a loopback STUN "
            "daemon, send a Binding Request with a non-zero transaction ID, "
            "lockstep a Binding Success that carries the stored transaction "
            "ID, independently poll the stored transaction ID on a later "
            "client socket, and read the sealed txid digest. Transaction-ID-"
            "gated exchanges stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "request": {"type": "boolean"},
                "success": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_txid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=STUN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def turn_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5766 TURN Allocate/Success route.

    Provider ``turn`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live relay silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="turn",
        description=(
            "Drive a first-class RFC 5766 session: bind a loopback TURN "
            "relay, send an Allocate with a non-empty nonce, lockstep an "
            "Allocation Success that carries the stored allocation nonce, "
            "independently poll the stored allocation nonce on a later "
            "client socket, and read the sealed relay digest. Nonce-gated "
            "exchanges stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "allocate": {"type": "boolean"},
                "success": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_nonce": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TURN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ice_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8445 ICE connectivity-check/nominate route.

    Provider ``ice`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live agent silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ice",
        description=(
            "Drive a first-class RFC 8445 session: bind a loopback ICE "
            "agent, send a connectivity-check with a non-empty ufrag, "
            "lockstep a nominated-pair Success that carries the stored "
            "candidate foundation, independently poll the stored candidate "
            "foundation on a later client socket, and read the sealed "
            "foundation digest. Ufrag-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "check": {"type": "boolean"},
                "nominate": {"type": "boolean"},
                "success": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ufrag": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ICE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dtls_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6347 DTLS ClientHello/Finished route.

    Provider ``dtls`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dtls",
        description=(
            "Drive a first-class RFC 6347 session: bind a loopback DTLS "
            "endpoint, send a ClientHello with a non-empty cookie, "
            "lockstep a Finished that carries the stored handshake "
            "cookie, independently poll the stored handshake cookie on a "
            "later client socket, and read the sealed cookie digest. "
            "Cookie-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "hello": {"type": "boolean"},
                "finished": {"type": "boolean"},
                "verify": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_cookie": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DTLS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def srtp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3711 SRTP Protect/Unprotect route.

    Provider ``srtp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="srtp",
        description=(
            "Drive a first-class RFC 3711 session: bind a loopback SRTP "
            "endpoint, send a Protect with a non-empty ssrc, "
            "lockstep an Unprotect that carries the stored packet "
            "roc, independently poll the stored packet roc on a "
            "later client socket, and read the sealed roc digest. "
            "SSRC-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "protect": {"type": "boolean"},
                "unprotect": {"type": "boolean"},
                "roc": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ssrc": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SRTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def sctp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4960 SCTP INIT/INIT-ACK route.

    Provider ``sctp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sctp",
        description=(
            "Drive a first-class RFC 4960 session: bind a loopback SCTP "
            "endpoint, send an INIT with a non-empty vtag, "
            "lockstep an INIT-ACK that carries the stored association "
            "tsn, independently poll the stored association tsn on a "
            "later client socket, and read the sealed tsn digest. "
            "Vtag-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "init": {"type": "boolean"},
                "init_ack": {"type": "boolean"},
                "tsn": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_vtag": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SCTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def datachannel_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8831 Data Channel OPEN/ACK route.

    Provider ``datachannel`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="datachannel",
        description=(
            "Drive a first-class RFC 8831 session: bind a loopback Data Channel "
            "endpoint, send an OPEN with a non-empty ppid, "
            "lockstep an ACK that carries the stored channel "
            "dcep, independently poll the stored channel dcep on a "
            "later client socket, and read the sealed dcep digest. "
            "PPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "open": {"type": "boolean"},
                "ack": {"type": "boolean"},
                "dcep": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ppid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DATACHANNEL_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def quic_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9000 QUIC INITIAL/HANDSHAKE route.

    Provider ``quic`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="quic",
        description=(
            "Drive a first-class RFC 9000 session: bind a loopback QUIC "
            "endpoint, send an INITIAL with a non-empty dcid, "
            "lockstep a HANDSHAKE that carries the stored packet "
            "pktnum, independently poll the stored packet pktnum on a "
            "later client socket, and read the sealed pktnum digest. "
            "DCID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "initial": {"type": "boolean"},
                "handshake": {"type": "boolean"},
                "pktnum": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dcid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=QUIC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def http3_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9114 HTTP/3 SETTINGS/HEADERS route.

    Provider ``http3`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="http3",
        description=(
            "Drive a first-class RFC 9114 session: bind a loopback HTTP/3 "
            "endpoint, send a SETTINGS with a non-empty streamid, "
            "lockstep a HEADERS that carries the stored stream "
            "qpack, independently poll the stored stream qpack on a "
            "later client socket, and read the sealed qpack digest. "
            "STREAMID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "settings": {"type": "boolean"},
                "headers": {"type": "boolean"},
                "qpack": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_streamid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTP3_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def webtransport_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9220 WebTransport CONNECT/SESSION route.

    Provider ``webtransport`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="webtransport",
        description=(
            "Drive a first-class RFC 9220 session: bind a loopback WebTransport "
            "endpoint, send a CONNECT with a non-empty sessionid, "
            "lockstep a SESSION that carries the stored session "
            "capsule, independently poll the stored session capsule on a "
            "later client socket, and read the sealed capsule digest. "
            "SESSIONID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "connect": {"type": "boolean"},
                "session": {"type": "boolean"},
                "capsule": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sessionid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBTRANSPORT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def datagram_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9221 QUIC DATAGRAM SEND/ECHO route.

    Provider ``datagram`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="datagram",
        description=(
            "Drive a first-class RFC 9221 session: bind a loopback QUIC DATAGRAM "
            "endpoint, send a SEND with a non-empty flowid, "
            "lockstep an ECHO that carries the stored flow "
            "contextid, independently poll the stored flow contextid on a "
            "later client socket, and read the sealed contextid digest. "
            "FLOWID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "send": {"type": "boolean"},
                "echo": {"type": "boolean"},
                "contextid": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_flowid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DATAGRAM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def masque_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9298 MASQUE CONNECT-UDP BIND/PROXY route.

    Provider ``masque`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="masque",
        description=(
            "Drive a first-class RFC 9298 session: bind a loopback MASQUE "
            "endpoint, send a BIND with a non-empty targetid, "
            "lockstep a PROXY that carries the stored proxy "
            "authority, independently poll the stored proxy authority on a "
            "later client socket, and read the sealed authority digest. "
            "TARGETID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "bind_cycle": {"type": "boolean"},
                "proxy": {"type": "boolean"},
                "authority": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_targetid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MASQUE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def connectip_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9484 CONNECT-IP ASSIGN/ADVERTISE route.

    Provider ``connectip`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="connectip",
        description=(
            "Drive a first-class RFC 9484 session: bind a loopback CONNECT-IP "
            "endpoint, send an ASSIGN with a non-empty prefixid, "
            "lockstep an ADVERTISE that carries the stored assigned "
            "ipaddr, independently poll the stored assigned ipaddr on a "
            "later client socket, and read the sealed ipaddr digest. "
            "PREFIXID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "assign_cycle": {"type": "boolean"},
                "advertise": {"type": "boolean"},
                "ipaddr": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_prefixid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=CONNECTIP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ohttp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9458 Oblivious HTTP ENCAPSULATE/DECAPSULATE route.

    Provider ``ohttp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ohttp",
        description=(
            "Drive a first-class RFC 9458 session: bind a loopback Oblivious HTTP "
            "gateway, send an ENCAPSULATE with a non-empty configid, "
            "lockstep a DECAPSULATE that carries the stored "
            "gateway, independently poll the stored gateway on a "
            "later client socket, and read the sealed gateway digest. "
            "CONFIGID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "encapsulate_cycle": {"type": "boolean"},
                "decapsulate": {"type": "boolean"},
                "gateway": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_configid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OHTTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ohsvcb_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9540 Oblivious Service Binding QUERY/ANSWER route.

    Provider ``ohsvcb`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ohsvcb",
        description=(
            "Drive a first-class RFC 9540 session: bind a loopback Oblivious Service "
            "Binding nameserver, send a QUERY with a non-empty svcbid, "
            "lockstep an ANSWER that carries the stored "
            "keyconf, independently poll the stored keyconf on a "
            "later client socket, and read the sealed keyconf digest. "
            "SVCBID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "query_cycle": {"type": "boolean"},
                "answer": {"type": "boolean"},
                "keyconf": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_svcbid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OHSVCB_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpsig_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9421 HTTP Message Signatures SIGN/VERIFY route.

    Provider ``httpsig`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpsig",
        description=(
            "Drive a first-class RFC 9421 session: bind a loopback HTTP Message "
            "Signatures origin, send a SIGN with a non-empty sigid, "
            "lockstep a VERIFY that carries the stored "
            "sigbase, independently poll the stored sigbase on a "
            "later client socket, and read the sealed sigbase digest. "
            "SIGID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "sign_cycle": {"type": "boolean"},
                "verify": {"type": "boolean"},
                "sigbase": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sigid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPSIG_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def digestfields_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9530 Digest Fields DIGEST/VERIFY route.

    Provider ``digestfields`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="digestfields",
        description=(
            "Drive a first-class RFC 9530 session: bind a loopback Digest Fields "
            "origin, send a DIGEST with a non-empty digestid, "
            "lockstep a VERIFY that carries the stored "
            "contentdigest, independently poll the stored contentdigest on a "
            "later client socket, and read the sealed contentdigest digest. "
            "DIGESTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "digest_cycle": {"type": "boolean"},
                "verify": {"type": "boolean"},
                "contentdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_digestid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DIGESTFIELDS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def bhttp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9292 Binary HTTP ENCODE/DECODE route.

    Provider ``bhttp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="bhttp",
        description=(
            "Drive a first-class RFC 9292 session: bind a loopback Binary HTTP "
            "origin, send an ENCODE with a non-empty messageid, "
            "lockstep a DECODE that carries the stored "
            "binarymsg, independently poll the stored binarymsg on a "
            "later client socket, and read the sealed binarymsg digest. "
            "MESSAGEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "encode_cycle": {"type": "boolean"},
                "decode": {"type": "boolean"},
                "binarymsg": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_messageid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BHTTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def http11_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9112 HTTP/1.1 PARSE/SERIALIZE route.

    Provider ``http11`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="http11",
        description=(
            "Drive a first-class RFC 9112 session: bind a loopback HTTP/1.1 "
            "origin, send a PARSE with a non-empty requestid, "
            "lockstep a SERIALIZE that carries the stored "
            "startline, independently poll the stored httpmessage startline on a "
            "later client socket, and read the sealed startline digest. "
            "REQUESTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "parse_cycle": {"type": "boolean"},
                "serialize": {"type": "boolean"},
                "startline": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_requestid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTP11_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def http2_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9113 HTTP/2 PREFACE/SETTINGS route.

    Provider ``http2`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="http2",
        description=(
            "Drive a first-class RFC 9113 session: bind a loopback HTTP/2 "
            "origin, send a PREFACE with a non-empty settingsid, "
            "lockstep a SETTINGS that carries the stored "
            "hpack, independently poll the stored connection preface on a "
            "later client socket, and read the sealed hpack digest. "
            "SETTINGSID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "preface_cycle": {"type": "boolean"},
                "settings": {"type": "boolean"},
                "hpack": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_settingsid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTP2_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpcache_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9111 HTTP Caching STORE/REVALIDATE route.

    Provider ``httpcache`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpcache",
        description=(
            "Drive a first-class RFC 9111 session: bind a loopback HTTP cache "
            "origin, send a STORE with a non-empty cacheid, "
            "lockstep a REVALIDATE that carries the stored "
            "freshness, independently poll the stored cache validator on a "
            "later client socket, and read the sealed freshness digest. "
            "CACHEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "store_cycle": {"type": "boolean"},
                "revalidate": {"type": "boolean"},
                "freshness": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_cacheid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPCACHE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpsemantics_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9110 HTTP Semantics GET/HEAD route.

    Provider ``httpsemantics`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpsemantics",
        description=(
            "Drive a first-class RFC 9110 session: bind a loopback HTTP Semantics "
            "origin, send a GET with a non-empty methodid, "
            "lockstep a HEAD that carries the stored "
            "fieldsection, independently poll the stored field section on a "
            "later client socket, and read the sealed fieldsection digest. "
            "METHODID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "get_cycle": {"type": "boolean"},
                "head": {"type": "boolean"},
                "fieldsection": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_methodid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPSMANTICS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def structuredfields_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8941 Structured Fields DICT/LIST route.

    Provider ``structuredfields`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="structuredfields",
        description=(
            "Drive a first-class RFC 8941 session: bind a loopback Structured Fields "
            "origin, send a DICT with a non-empty dictid, "
            "lockstep a LIST that carries the stored "
            "sfv, independently poll the stored sfv on a "
            "later client socket, and read the sealed sfv digest. "
            "DICTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dict_cycle": {"type": "boolean"},
                "list": {"type": "boolean"},
                "sfv": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dictid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=STRUCTUREDFIELDS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def clienthints_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8942 HTTP Client Hints ACCEPTCH/CRITCH route.

    Provider ``clienthints`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="clienthints",
        description=(
            "Drive a first-class RFC 8942 session: bind a loopback Client Hints "
            "origin, send an ACCEPTCH with a non-empty chid, "
            "lockstep a CRITCH that carries the stored "
            "hintsdigest, independently poll the stored hintsdigest on a "
            "later client socket, and read the sealed hintsdigest. "
            "CHID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "acceptch": {"type": "boolean"},
                "critch": {"type": "boolean"},
                "hintsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_chid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=CLIENTHINTS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def earlyhints_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8297 Early Hints LINK/HINT route.

    Provider ``earlyhints`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="earlyhints",
        description=(
            "Drive a first-class RFC 8297 session: bind a loopback Early Hints "
            "origin, send a LINK with a non-empty linkid, "
            "lockstep a HINT that carries the stored "
            "earlydigest, independently poll the stored earlydigest on a "
            "later client socket, and read the sealed earlydigest. "
            "LINKID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "link": {"type": "boolean"},
                "hint": {"type": "boolean"},
                "earlydigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_linkid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EARLYHINTS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def encryptedcontent_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8188 Encrypted Content-Encoding ENCRYPT/DECRYPT route.

    Provider ``encryptedcontent`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="encryptedcontent",
        description=(
            "Drive a first-class RFC 8188 session: bind a loopback Encrypted "
            "Content-Encoding origin, send an ENCRYPT with a non-empty encid, "
            "lockstep a DECRYPT that carries the stored "
            "ecedigest, independently poll the stored ecedigest on a "
            "later client socket, and read the sealed ecedigest. "
            "ENCID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "encrypt": {"type": "boolean"},
                "decrypt": {"type": "boolean"},
                "ecedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_encid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ENCRYPTEDCONTENT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def altsvc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7838 HTTP Alternative Services ALTSVC/ORIGIN route.

    Provider ``altsvc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="altsvc",
        description=(
            "Drive a first-class RFC 7838 session: bind a loopback HTTP "
            "Alternative Services origin, send an ALTSVC with a non-empty altsvcid, "
            "lockstep an ORIGIN that carries the stored "
            "origindigest, independently poll the stored origindigest on a "
            "later client socket, and read the sealed origindigest. "
            "ALTSVCID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "altsvc": {"type": "boolean"},
                "origin": {"type": "boolean"},
                "origindigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_altsvcid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ALTSVC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def hsts_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6797 HTTP Strict Transport Security STS/PRELOAD route.

    Provider ``hsts`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="hsts",
        description=(
            "Drive a first-class RFC 6797 session: bind a loopback HTTP "
            "Strict Transport Security origin, send an STS with a non-empty hstsid, "
            "lockstep a PRELOAD that carries the stored "
            "stsdigest, independently poll the stored stsdigest on a "
            "later client socket, and read the sealed stsdigest. "
            "HSTSID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "sts": {"type": "boolean"},
                "preload": {"type": "boolean"},
                "stsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_hstsid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HSTS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def hpkp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7469 HTTP Public Key Pinning PIN/REPORT route.

    Provider ``hpkp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="hpkp",
        description=(
            "Drive a first-class RFC 7469 session: bind a loopback HTTP "
            "Public Key Pinning origin, send a PIN with a non-empty pinid, "
            "lockstep a REPORT that carries the stored "
            "pindigest, independently poll the stored pindigest on a "
            "later client socket, and read the sealed pindigest. "
            "PINID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "pin": {"type": "boolean"},
                "report": {"type": "boolean"},
                "pindigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pinid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HPKP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def expectct_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9163 Expect-CT EXPECT/REPORT route.

    Provider ``expectct`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="expectct",
        description=(
            "Drive a first-class RFC 9163 session: bind a loopback Expect-CT "
            "origin, send an EXPECT with a non-empty ctid, "
            "lockstep a REPORT that carries the stored "
            "ctdigest, independently poll the stored ctdigest on a "
            "later client socket, and read the sealed ctdigest. "
            "CTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "expect": {"type": "boolean"},
                "report": {"type": "boolean"},
                "ctdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ctid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EXPECTCT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def xfo_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7034 X-Frame-Options DENY/SAMEORIGIN route.

    Provider ``xfo`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="xfo",
        description=(
            "Drive a first-class RFC 7034 session: bind a loopback X-Frame-Options "
            "origin, send a DENY with a non-empty frameid, "
            "lockstep a SAMEORIGIN that carries the stored "
            "framedigest, independently poll the stored framedigest on a "
            "later client socket, and read the sealed framedigest. "
            "FRAMEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "deny": {"type": "boolean"},
                "sameorigin": {"type": "boolean"},
                "framedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_frameid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=XFO_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def weborigin_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6454 Web Origin SERIALIZE/TUPLE route.

    Provider ``weborigin`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="weborigin",
        description=(
            "Drive a first-class RFC 6454 session: bind a loopback Web Origin "
            "origin, send a SERIALIZE with a non-empty tupleid, "
            "lockstep a TUPLE that carries the stored "
            "tupledigest, independently poll the stored tupledigest on a "
            "later client socket, and read the sealed tupledigest. "
            "TUPLEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "serialize": {"type": "boolean"},
                "tuple": {"type": "boolean"},
                "tupledigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_tupleid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBORIGIN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpcookie_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6265 HTTP State Management SET-COOKIE/COOKIE route.

    Provider ``httpcookie`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpcookie",
        description=(
            "Drive a first-class RFC 6265 session: bind a loopback HTTP cookie "
            "origin, send a SET-COOKIE with a non-empty cookieid, "
            "lockstep a COOKIE that carries the stored "
            "cookiedigest, independently poll the stored cookiedigest on a "
            "later client socket, and read the sealed cookiedigest. "
            "COOKIEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "setcookie": {"type": "boolean"},
                "cookie": {"type": "boolean"},
                "cookiedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_cookieid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPCOOKIE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def contentdisposition_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6266 Content-Disposition DISPOSITION/ATTACHMENT route.

    Provider ``contentdisposition`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="contentdisposition",
        description=(
            "Drive a first-class RFC 6266 session: bind a loopback Content-Disposition "
            "origin, send a DISPOSITION with a non-empty dispositionid, "
            "lockstep an ATTACHMENT that carries the stored "
            "dispositiondigest, independently poll the stored dispositiondigest on a "
            "later client socket, and read the sealed dispositiondigest. "
            "DISPOSITIONID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "disposition": {"type": "boolean"},
                "attachment": {"type": "boolean"},
                "dispositiondigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dispositionid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=CONTENTDISPOSITION_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def weblinking_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5988 Web Linking LINK/RELATION route.

    Provider ``weblinking`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="weblinking",
        description=(
            "Drive a first-class RFC 5988 session: bind a loopback Web Linking "
            "origin, send a LINK with a non-empty relationid, "
            "lockstep a RELATION that carries the stored "
            "relationdigest, independently poll the stored relationdigest on a "
            "later client socket, and read the sealed relationdigest. "
            "RELATIONID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "link": {"type": "boolean"},
                "relation": {"type": "boolean"},
                "relationdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_relationid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBLINKING_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def extvalue_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5987 Character Set and Language Encoding ENCODING/LANGUAGE route.

    Provider ``extvalue`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="extvalue",
        description=(
            "Drive a first-class RFC 5987 session: bind a loopback Character Set "
            "and Language Encoding origin, send an ENCODING with a non-empty charsetid, "
            "lockstep a LANGUAGE that carries the stored "
            "charsetdigest, independently poll the stored charsetdigest on a "
            "later client socket, and read the sealed charsetdigest. "
            "CHARSETID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "encoding": {"type": "boolean"},
                "language": {"type": "boolean"},
                "charsetdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_charsetid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EXTVALUE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def stalecontent_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5861 HTTP Cache-Control Extensions for Stale Content STALE/IFERROR route.

    Provider ``stalecontent`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="stalecontent",
        description=(
            "Drive a first-class RFC 5861 session: bind a loopback HTTP Cache-Control "
            "Extensions for Stale Content origin, send a STALE with a non-empty staleid, "
            "lockstep an IFERROR that carries the stored "
            "staledigest, independently poll the stored staledigest on a "
            "later client socket, and read the sealed staledigest. "
            "STALEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "stale": {"type": "boolean"},
                "iferror": {"type": "boolean"},
                "staledigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_staleid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=STALECONTENT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httppatch_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5789 PATCH Method for HTTP PATCH/ENTITY route.

    Provider ``httppatch`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httppatch",
        description=(
            "Drive a first-class RFC 5789 session: bind a loopback PATCH Method "
            "for HTTP origin, send a PATCH with a non-empty patchid, "
            "lockstep an ENTITY that carries the stored "
            "patchdigest, independently poll the stored patchdigest on a "
            "later client socket, and read the sealed patchdigest. "
            "PATCHID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "patch": {"type": "boolean"},
                "entity": {"type": "boolean"},
                "patchdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_patchid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPPATCH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def wellknown_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5785 Defining Well-Known Uniform Resource Identifiers DISCOVERY/SUFFIX route.

    Provider ``wellknown`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="wellknown",
        description=(
            "Drive a first-class RFC 5785 session: bind a loopback Defining Well-Known "
            "Uniform Resource Identifiers origin, send a DISCOVERY with a non-empty suffixid, "
            "lockstep a SUFFIX that carries the stored "
            "suffixdigest, independently poll the stored suffixdigest on a "
            "later client socket, and read the sealed suffixdigest. "
            "SUFFIXID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "discovery": {"type": "boolean"},
                "suffix": {"type": "boolean"},
                "suffixdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_suffixid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WELLKNOWN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def webdav_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4918 HTTP Extensions for WebDAV PROPFIND/LOCK route.

    Provider ``webdav`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="webdav",
        description=(
            "Drive a first-class RFC 4918 session: bind a loopback HTTP Extensions "
            "for WebDAV origin, send a PROPFIND with a non-empty lockid, "
            "lockstep a LOCK that carries the stored "
            "lockdigest, independently poll the stored lockdigest on a "
            "later client socket, and read the sealed lockdigest. "
            "LOCKID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "propfind": {"type": "boolean"},
                "lock": {"type": "boolean"},
                "lockdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lockid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WEBDAV_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def spnego_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4559 SPNEGO NEGOTIATE/AUTHENTICATE route.

    Provider ``spnego`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="spnego",
        description=(
            "Drive a first-class RFC 4559 session: bind a loopback SPNEGO-based "
            "Kerberos and NTLM HTTP Authentication origin, send a NEGOTIATE with "
            "a non-empty negotiateid, lockstep an AUTHENTICATE that carries the "
            "stored negotiatedigest, independently poll the stored negotiatedigest "
            "on a later client socket, and read the sealed negotiatedigest. "
            "NEGOTIATEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "negotiate": {"type": "boolean"},
                "authenticate": {"type": "boolean"},
                "negotiatedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_negotiateid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SPNEGO_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httptls_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2817 HTTP Upgrade to TLS UPGRADE/TLS route.

    Provider ``httptls`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httptls",
        description=(
            "Drive a first-class RFC 2817 session: bind a loopback Upgrading to "
            "TLS Within HTTP/1.1 origin, send a UPGRADE with a non-empty "
            "upgradeid, lockstep a TLS that carries the stored "
            "upgradetlsdigest, independently poll the stored upgradetlsdigest "
            "on a later client socket, and read the sealed upgradetlsdigest. "
            "UPGRADEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "upgrade": {"type": "boolean"},
                "tls": {"type": "boolean"},
                "upgradetlsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_upgradeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPTLS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpauth_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2617 HTTP Authentication AUTH/DIGEST route.

    Provider ``httpauth`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpauth",
        description=(
            "Drive a first-class RFC 2617 session: bind a loopback HTTP "
            "Authentication origin, send an AUTH with a non-empty "
            "nonceid, lockstep a DIGEST that carries the stored "
            "authdigest, independently poll the stored authdigest "
            "on a later client socket, and read the sealed authdigest. "
            "NONCEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "auth": {"type": "boolean"},
                "digest": {"type": "boolean"},
                "authdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_nonceid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPAUTH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def tcn_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2295 Transparent Content Negotiation ALTERNATES/CHOICE route.

    Provider ``tcn`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="tcn",
        description=(
            "Drive a first-class RFC 2295 session: bind a loopback Transparent "
            "Content Negotiation origin, send an ALTERNATES with a non-empty "
            "variantid, lockstep a CHOICE that carries the stored "
            "choicedigest, independently poll the stored choicedigest "
            "on a later client socket, and read the sealed choicedigest. "
            "VARIANTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "alternates": {"type": "boolean"},
                "choice": {"type": "boolean"},
                "choicedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_variantid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TCN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def hitmeter_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2227 Simple Hit-Metering METER/USAGE route.

    Provider ``hitmeter`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="hitmeter",
        description=(
            "Drive a first-class RFC 2227 session: bind a loopback Simple "
            "Hit-Metering origin, send a METER with a non-empty "
            "meterid, lockstep a USAGE that carries the stored "
            "usagedigest, independently poll the stored usagedigest "
            "on a later client socket, and read the sealed usagedigest. "
            "METERID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "meter": {"type": "boolean"},
                "usage": {"type": "boolean"},
                "usagedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_meterid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HITMETER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def icp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2186 Internet Cache Protocol QUERY/HIT route.

    Provider ``icp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="icp",
        description=(
            "Drive a first-class RFC 2186 session: bind a loopback Internet "
            "Cache Protocol origin, send a QUERY with a non-empty "
            "queryid, lockstep a HIT that carries the stored "
            "icpdigest, independently poll the stored icpdigest "
            "on a later client socket, and read the sealed icpdigest. "
            "QUERYID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "query": {"type": "boolean"},
                "hit": {"type": "boolean"},
                "icpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_queryid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ICP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpver_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2145 HTTP Version Numbers VERSION/INTERPRET route.

    Provider ``httpver`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpver",
        description=(
            "Drive a first-class RFC 2145 session: bind a loopback HTTP "
            "version origin, send a VERSION with a non-empty "
            "versionid, lockstep an INTERPRET that carries the stored "
            "versiondigest, independently poll the stored versiondigest "
            "on a later client socket, and read the sealed versiondigest. "
            "VERSIONID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "version": {"type": "boolean"},
                "interpret": {"type": "boolean"},
                "versiondigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_versionid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPVER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def httpstate_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2109 HTTP State Management OFFER/ATTACH route.

    Provider ``httpstate`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="httpstate",
        description=(
            "Drive a first-class RFC 2109 session: bind a loopback HTTP "
            "state origin, send an OFFER with a non-empty "
            "stateid, lockstep an ATTACH that carries the stored "
            "statedigest, independently poll the stored statedigest "
            "on a later client socket, and read the sealed statedigest. "
            "STATEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "offer": {"type": "boolean"},
                "attach": {"type": "boolean"},
                "statedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_stateid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTPSTATE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def digestauth_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2069 Digest Access Authentication CHALLENGE/RESPONSE route.

    Provider ``digestauth`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="digestauth",
        description=(
            "Drive a first-class RFC 2069 session: bind a loopback HTTP "
            "digest origin, send a CHALLENGE with a non-empty "
            "challengeid, lockstep a RESPONSE that carries the stored "
            "responsedigest, independently poll the stored responsedigest "
            "on a later client socket, and read the sealed responsedigest. "
            "CHALLENGEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "challenge": {"type": "boolean"},
                "response": {"type": "boolean"},
                "responsedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_challengeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DIGESTAUTH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def http10_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1945 HTTP/1.0 GET/POST route.

    Provider ``http10`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="http10",
        description=(
            "Drive a first-class RFC 1945 session: bind a loopback HTTP/1.0 "
            "origin, send a GET with a non-empty "
            "http10id, lockstep a POST that carries the stored "
            "http10digest, independently poll the stored http10digest "
            "on a later client socket, and read the sealed http10digest. "
            "HTTP10ID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "get": {"type": "boolean"},
                "post": {"type": "boolean"},
                "http10digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_http10id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=HTTP10_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def url_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1738 URL RESOLVE/LOCATE route.

    Provider ``url`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="url",
        description=(
            "Drive a first-class RFC 1738 session: bind a loopback URL "
            "origin, send a RESOLVE with a non-empty "
            "urlid, lockstep a LOCATE that carries the stored "
            "urldigest, independently poll the stored urldigest "
            "on a later client socket, and read the sealed urldigest. "
            "URLID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "resolve": {"type": "boolean"},
                "locate": {"type": "boolean"},
                "urldigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_urlid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=URL_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def uri_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1630 URI IDENTIFY/DEREF route.

    Provider ``uri`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="uri",
        description=(
            "Drive a first-class RFC 1630 session: bind a loopback URI "
            "origin, send an IDENTIFY with a non-empty "
            "uriid, lockstep a DEREF that carries the stored "
            "uridigest, independently poll the stored uridigest "
            "on a later client socket, and read the sealed uridigest. "
            "URIID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "identify": {"type": "boolean"},
                "deref": {"type": "boolean"},
                "uridigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_uriid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=URI_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mime_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1521 MIME BODY/TRANSFER route.

    Provider ``mime`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mime",
        description=(
            "Drive a first-class RFC 1521 session: bind a loopback MIME "
            "origin, send a BODY with a non-empty "
            "mimeid, lockstep a TRANSFER that carries the stored "
            "mimedigest, independently poll the stored mimedigest "
            "on a later client socket, and read the sealed mimedigest. "
            "MIMEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "body": {"type": "boolean"},
                "transfer": {"type": "boolean"},
                "mimedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mimeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MIME_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def gopher_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1436 Gopher SELECTOR/MENU route.

    Provider ``gopher`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="gopher",
        description=(
            "Drive a first-class RFC 1436 session: bind a loopback Gopher "
            "origin, send a SELECTOR with a non-empty "
            "gopherid, lockstep a MENU that carries the stored "
            "gopherdigest, independently poll the stored gopherdigest "
            "on a later client socket, and read the sealed gopherdigest. "
            "GOPHERID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "selector": {"type": "boolean"},
                "menu": {"type": "boolean"},
                "gopherdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_gopherid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GOPHER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def finger_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1288 Finger QUERY/USER route.

    Provider ``finger`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="finger",
        description=(
            "Drive a first-class RFC 1288 session: bind a loopback Finger "
            "origin, send a QUERY with a non-empty "
            "fingerid, lockstep a USER that carries the stored "
            "fingerdigest, independently poll the stored fingerdigest "
            "on a later client socket, and read the sealed fingerdigest. "
            "FINGERID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "query": {"type": "boolean"},
                "user": {"type": "boolean"},
                "fingerdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_fingerid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=FINGER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lpd_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1179 LPD PRINT/QUEUE route.

    Provider ``lpd`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lpd",
        description=(
            "Drive a first-class RFC 1179 session: bind a loopback Line Printer "
            "Daemon origin, send a PRINT with a non-empty "
            "lpdid, lockstep a QUEUE that carries the stored "
            "lpddigest, independently poll the stored lpddigest "
            "on a later client socket, and read the sealed lpddigest. "
            "LPDID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "print": {"type": "boolean"},
                "queue": {"type": "boolean"},
                "lpddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lpdid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LPD_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def nntp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 977 NNTP ARTICLE/GROUP route.

    Provider ``nntp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="nntp",
        description=(
            "Drive a first-class RFC 977 session: bind a loopback Network News "
            "Transfer Protocol origin, send an ARTICLE with a non-empty "
            "nntpid, lockstep a GROUP that carries the stored "
            "nntpdigest, independently poll the stored nntpdigest "
            "on a later client socket, and read the sealed nntpdigest. "
            "NNTPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "article": {"type": "boolean"},
                "group": {"type": "boolean"},
                "nntpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_nntpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=NNTP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def telnet_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 854 TELNET DO/WILL route.

    Provider ``telnet`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="telnet",
        description=(
            "Drive a first-class RFC 854 session: bind a loopback Telnet "
            "Protocol Specification origin, send a DO with a non-empty "
            "telnetid, lockstep a WILL that carries the stored "
            "telnetdigest, independently poll the stored telnetdigest "
            "on a later client socket, and read the sealed telnetdigest. "
            "TELNETID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "do": {"type": "boolean"},
                "will": {"type": "boolean"},
                "telnetdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_telnetid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TELNET_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def tcp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 793 TCP SYN/ACK route.

    Provider ``tcp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="tcp",
        description=(
            "Drive a first-class RFC 793 session: bind a loopback Transmission "
            "Control Protocol origin, send a SYN with a non-empty "
            "tcpid, lockstep an ACK that carries the stored "
            "tcpdigest, independently poll the stored tcpdigest "
            "on a later client socket, and read the sealed tcpdigest. "
            "TCPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "syn": {"type": "boolean"},
                "ack": {"type": "boolean"},
                "tcpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_tcpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TCP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def udp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 768 UDP SEND/RECV route.

    Provider ``udp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="udp",
        description=(
            "Drive a first-class RFC 768 session: bind a loopback User "
            "Datagram Protocol origin, send a SEND with a non-empty "
            "udpid, lockstep a RECV that carries the stored "
            "udpdigest, independently poll the stored udpdigest "
            "on a later client socket, and read the sealed udpdigest. "
            "UDPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "send": {"type": "boolean"},
                "recv": {"type": "boolean"},
                "udpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_udpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=UDP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def icmp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 792 ICMP ECHO/REPLY route.

    Provider ``icmp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="icmp",
        description=(
            "Drive a first-class RFC 792 session: bind a loopback Internet "
            "Control Message Protocol origin, send an ECHO with a non-empty "
            "icmpid, lockstep a REPLY that carries the stored "
            "icmpdigest, independently poll the stored icmpdigest "
            "on a later client socket, and read the sealed icmpdigest. "
            "ICMPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "echo": {"type": "boolean"},
                "reply": {"type": "boolean"},
                "icmpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_icmpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ICMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ip_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 791 IP DATAGRAM/FRAGMENT route.

    Provider ``ip`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ip",
        description=(
            "Drive a first-class RFC 791 session: bind a loopback Internet "
            "Protocol origin, send a DATAGRAM with a non-empty "
            "ipid, lockstep a FRAGMENT that carries the stored "
            "ipdigest, independently poll the stored ipdigest "
            "on a later client socket, and read the sealed ipdigest. "
            "IPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "datagram": {"type": "boolean"},
                "fragment": {"type": "boolean"},
                "ipdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ipid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def arp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 826 ARP REQUEST/REPLY route.

    Provider ``arp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="arp",
        description=(
            "Drive a first-class RFC 826 session: bind a loopback Address "
            "Resolution Protocol origin, send a REQUEST with a non-empty "
            "arpid, lockstep a REPLY that carries the stored "
            "arpdigest, independently poll the stored arpdigest "
            "on a later client socket, and read the sealed arpdigest. "
            "ARPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "request": {"type": "boolean"},
                "reply": {"type": "boolean"},
                "arpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_arpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ARP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def rarp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 903 RARP REVERSE/REPLY route.

    Provider ``rarp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="rarp",
        description=(
            "Drive a first-class RFC 903 session: bind a loopback Reverse "
            "Address Resolution Protocol origin, send a REVERSE with a non-empty "
            "rarpid, lockstep a REPLY that carries the stored "
            "rarpdigest, independently poll the stored rarpdigest "
            "on a later client socket, and read the sealed rarpdigest. "
            "RARPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "reverse": {"type": "boolean"},
                "reply": {"type": "boolean"},
                "rarpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_rarpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RARP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def igmp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1112 IGMP QUERY/REPORT route.

    Provider ``igmp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="igmp",
        description=(
            "Drive a first-class RFC 1112 session: bind a loopback Internet "
            "Group Management Protocol origin, send a QUERY with a non-empty "
            "igmpid, lockstep a REPORT that carries the stored "
            "igmpdigest, independently poll the stored igmpdigest "
            "on a later client socket, and read the sealed igmpdigest. "
            "IGMPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "query": {"type": "boolean"},
                "report": {"type": "boolean"},
                "igmpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_igmpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IGMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mld_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2710 MLD LISTENER/DONE route.

    Provider ``mld`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mld",
        description=(
            "Drive a first-class RFC 2710 session: bind a loopback Multicast "
            "Listener Discovery origin, send a LISTENER with a non-empty "
            "mldid, lockstep a DONE that carries the stored "
            "mlddigest, independently poll the stored mlddigest "
            "on a later client socket, and read the sealed mlddigest. "
            "MLDID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "listener": {"type": "boolean"},
                "done": {"type": "boolean"},
                "mlddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mldid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MLD_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ndp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4861 NDP SOLICIT/ADVERT route.

    Provider ``ndp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ndp",
        description=(
            "Drive a first-class RFC 4861 session: bind a loopback Neighbor "
            "Discovery Protocol origin, send a SOLICIT with a non-empty "
            "ndpid, lockstep an ADVERT that carries the stored "
            "ndpdigest, independently poll the stored ndpdigest "
            "on a later client socket, and read the sealed ndpdigest. "
            "NDPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "solicit": {"type": "boolean"},
                "advert": {"type": "boolean"},
                "ndpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ndpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=NDP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def slaac_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4862 SLAAC ROUTER/PREFIX route.

    Provider ``slaac`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="slaac",
        description=(
            "Drive a first-class RFC 4862 session: bind a loopback IPv6 "
            "Stateless Address Autoconfiguration origin, send a ROUTER with a "
            "non-empty slaacid, lockstep a PREFIX that carries the stored "
            "slaacdigest, independently poll the stored slaacdigest "
            "on a later client socket, and read the sealed slaacdigest. "
            "SLAACID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "router": {"type": "boolean"},
                "prefix": {"type": "boolean"},
                "slaacdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_slaacid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SLAAC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def tempaddr_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4941 Privacy Extensions TEMPORARY/PUBLIC route.

    Provider ``tempaddr`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="tempaddr",
        description=(
            "Drive a first-class RFC 4941 session: bind a loopback Privacy "
            "Extensions origin, send a TEMPORARY with a "
            "non-empty tempaddrid, lockstep a PUBLIC that carries the stored "
            "tempaddrdigest, independently poll the stored tempaddrdigest "
            "on a later client socket, and read the sealed tempaddrdigest. "
            "TEMPADDRID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "temporary": {"type": "boolean"},
                "public": {"type": "boolean"},
                "tempaddrdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_tempaddrid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TEMPADDR_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def opaqueiid_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7217 Opaque IID STABLE/OPAQUE route.

    Provider ``opaqueiid`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="opaqueiid",
        description=(
            "Drive a first-class RFC 7217 session: bind a loopback Semantically "
            "Opaque Interface Identifiers origin, send a STABLE with a "
            "non-empty opaqueid, lockstep an OPAQUE that carries the stored "
            "opaquedigest, independently poll the stored opaquedigest "
            "on a later client socket, and read the sealed opaquedigest. "
            "OPAQUEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "stable": {"type": "boolean"},
                "opaque": {"type": "boolean"},
                "opaquedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_opaqueid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OPAQUEIID_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def cga_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3972 CGA GENERATE/VERIFY route.

    Provider ``cga`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="cga",
        description=(
            "Drive a first-class RFC 3972 session: bind a loopback Cryptographically "
            "Generated Addresses origin, send a GENERATE with a "
            "non-empty cgaid, lockstep a VERIFY that carries the stored "
            "cgadigest, independently poll the stored cgadigest "
            "on a later client socket, and read the sealed cgadigest. "
            "CGAID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "generate": {"type": "boolean"},
                "verify": {"type": "boolean"},
                "cgadigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_cgaid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=CGA_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def send_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3971 SEND CPS/CPA route.

    Provider ``send`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="send",
        description=(
            "Drive a first-class RFC 3971 session: bind a loopback SEcure "
            "Neighbor Discovery origin, send a CPS with a "
            "non-empty sendid, lockstep a CPA that carries the stored "
            "senddigest, independently poll the stored senddigest "
            "on a later client socket, and read the sealed senddigest. "
            "SENDID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "cps": {"type": "boolean"},
                "cpa": {"type": "boolean"},
                "senddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sendid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SEND_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ula_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4193 ULA UNIQUE/LOCAL route.

    Provider ``ula`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ula",
        description=(
            "Drive a first-class RFC 4193 session: bind a loopback Unique Local "
            "IPv6 Unicast Addresses origin, send a UNIQUE with a "
            "non-empty ulaid, lockstep a LOCAL that carries the stored "
            "uladigest, independently poll the stored uladigest "
            "on a later client socket, and read the sealed uladigest. "
            "ULAID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "unique": {"type": "boolean"},
                "local": {"type": "boolean"},
                "uladigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ulaid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ULA_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ipv6addr_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4291 IPv6 Addressing Architecture GLOBAL/UNICAST route.

    Provider ``ipv6addr`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ipv6addr",
        description=(
            "Drive a first-class RFC 4291 session: bind a loopback IPv6 "
            "Addressing Architecture origin, send a GLOBAL with a "
            "non-empty ipv6addrid, lockstep a UNICAST that carries the stored "
            "ipv6addrdigest, independently poll the stored ipv6addrdigest "
            "on a later client socket, and read the sealed ipv6addrdigest. "
            "IPV6ADDRID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "global": {"type": "boolean"},
                "unicast": {"type": "boolean"},
                "ipv6addrdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ipv6addrid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IPV6ADDR_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ipv6scope_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4007 IPv6 Scoped Address Architecture SCOPE/ZONE route.

    Provider ``ipv6scope`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ipv6scope",
        description=(
            "Drive a first-class RFC 4007 session: bind a loopback IPv6 "
            "Scoped Address Architecture origin, send a SCOPE with a "
            "non-empty scopeid, lockstep a ZONE that carries the stored "
            "scopedigest, independently poll the stored scopedigest "
            "on a later client socket, and read the sealed scopedigest. "
            "SCOPEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "scope": {"type": "boolean"},
                "zone": {"type": "boolean"},
                "scopedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_scopeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IPV6SCOPE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def addrselect_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6724 Default Address Selection SOURCE/DEST route.

    Provider ``addrselect`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="addrselect",
        description=(
            "Drive a first-class RFC 6724 session: bind a loopback IPv6 "
            "Default Address Selection origin, send a SOURCE with a "
            "non-empty selectid, lockstep a DEST that carries the stored "
            "selectdigest, independently poll the stored selectdigest "
            "on a later client socket, and read the sealed selectdigest. "
            "SELECTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "source": {"type": "boolean"},
                "dest": {"type": "boolean"},
                "selectdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_selectid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ADDRSELECT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def addrpolicy_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7078 Address Selection Policy POLICY/TABLE route.

    Provider ``addrpolicy`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="addrpolicy",
        description=(
            "Drive a first-class RFC 7078 session: bind a loopback DHCPv6 "
            "Address Selection Policy origin, send a POLICY with a "
            "non-empty policyid, lockstep a TABLE that carries the stored "
            "policydigest, independently poll the stored policydigest "
            "on a later client socket, and read the sealed policydigest. "
            "POLICYID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "policy": {"type": "boolean"},
                "table": {"type": "boolean"},
                "policydigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_policyid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ADDRPOLICY_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def firsthop_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8028 First-Hop Router Selection FIRST/HOP route.

    Provider ``firsthop`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="firsthop",
        description=(
            "Drive a first-class RFC 8028 session: bind a loopback IPv6 "
            "First-Hop Router Selection origin, send a FIRST with a "
            "non-empty hopid, lockstep a HOP that carries the stored "
            "hopdigest, independently poll the stored hopdigest "
            "on a later client socket, and read the sealed hopdigest. "
            "HOPID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "first": {"type": "boolean"},
                "hop": {"type": "boolean"},
                "hopdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_hopid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=FIRSTHOP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def rdnss_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8106 RDNSS/DNSSL route.

    Provider ``rdnss`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="rdnss",
        description=(
            "Drive a first-class RFC 8106 session: bind a loopback IPv6 "
            "Router Advertisement DNS Configuration origin, send a RDNSS with a "
            "non-empty rdnssid, lockstep a DNSSL that carries the stored "
            "rdnssdigest, independently poll the stored rdnssdigest "
            "on a later client socket, and read the sealed rdnssdigest. "
            "RDNSSID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "rdnss": {"type": "boolean"},
                "dnssl": {"type": "boolean"},
                "rdnssdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_rdnssid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RDNSS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pref64_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8781 PREF64/PREFIX route.

    Provider ``pref64`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pref64",
        description=(
            "Drive a first-class RFC 8781 session: bind a loopback Discovering "
            "PREF64 in Router Advertisements origin, send a PREF64 with a "
            "non-empty pref64id, lockstep a PREFIX that carries the stored "
            "pref64digest, independently poll the stored pref64digest "
            "on a later client socket, and read the sealed pref64digest. "
            "PREF64ID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "pref64": {"type": "boolean"},
                "prefix": {"type": "boolean"},
                "pref64digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pref64id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PREF64_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def nat64_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6146 NAT64/SESSION route.

    Provider ``nat64`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="nat64",
        description=(
            "Drive a first-class RFC 6146 session: bind a loopback Stateful "
            "NAT64 origin, send a NAT64 with a "
            "non-empty nat64id, lockstep a SESSION that carries the stored "
            "nat64digest, independently poll the stored nat64digest "
            "on a later client socket, and read the sealed nat64digest. "
            "NAT64ID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "nat64": {"type": "boolean"},
                "session": {"type": "boolean"},
                "nat64digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_nat64id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=NAT64_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dns64_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6147 DNS64/SYNTH route.

    Provider ``dns64`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dns64",
        description=(
            "Drive a first-class RFC 6147 session: bind a loopback DNS "
            "Extensions for Network Address Translation from IPv6 Clients to "
            "IPv4 Servers origin, send a DNS64 with a "
            "non-empty dns64id, lockstep a SYNTH that carries the stored "
            "dns64digest, independently poll the stored dns64digest "
            "on a later client socket, and read the sealed dns64digest. "
            "DNS64ID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dns64": {"type": "boolean"},
                "synth": {"type": "boolean"},
                "dns64digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dns64id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DNS64_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def xlat_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6877 CLAT/PLAT route.

    Provider ``xlat`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="xlat",
        description=(
            "Drive a first-class RFC 6877 session: bind a loopback 464XLAT "
            "Combination of Stateful and Stateless Translation origin, send a "
            "CLAT with a non-empty clatid, lockstep a PLAT that carries the "
            "stored clatdigest, independently poll the stored clatdigest "
            "on a later client socket, and read the sealed clatdigest. "
            "CLATID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "clat": {"type": "boolean"},
                "plat": {"type": "boolean"},
                "clatdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_clatid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=XLAT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def disc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7050 IPV4ONLY/AAAA route.

    Provider ``disc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="disc",
        description=(
            "Drive a first-class RFC 7050 session: bind a loopback Discovery "
            "of the IPv6 Prefix Used for IPv6 Address Synthesis origin, send a "
            "IPV4ONLY with a non-empty discid, lockstep a AAAA that carries the "
            "stored discdigest, independently poll the stored discdigest "
            "on a later client socket, and read the sealed discdigest. "
            "DISCID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "ipv4only": {"type": "boolean"},
                "aaaa": {"type": "boolean"},
                "discdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_discid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DISC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dslite_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6333 Dual-Stack Lite B4/AFTR route.

    Provider ``dslite`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dslite",
        description=(
            "Drive a first-class RFC 6333 session: bind a loopback Dual-Stack "
            "Lite Broadband Deployments Following IPv4 Exhaustion origin, send a "
            "B4 with a non-empty dsliteid, lockstep an AFTR that carries the "
            "stored dslitedigest, independently poll the stored dslitedigest "
            "on a later client socket, and read the sealed dslitedigest. "
            "DSLITEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "b4": {"type": "boolean"},
                "aftr": {"type": "boolean"},
                "dslitedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dsliteid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DSLITE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lw4o6_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7596 Lightweight 4over6 BINDING/PORTSET route.

    Provider ``lw4o6`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lw4o6",
        description=(
            "Drive a first-class RFC 7596 session: bind a loopback Lightweight "
            "4over6 An Extension to the Dual-Stack Lite Architecture origin, send a "
            "BINDING with a non-empty lw4o6id, lockstep a PORTSET that carries the "
            "stored lw4o6digest, independently poll the stored lw4o6digest "
            "on a later client socket, and read the sealed lw4o6digest. "
            "LW4O6ID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "binding": {"type": "boolean"},
                "portset": {"type": "boolean"},
                "lw4o6digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lw4o6id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LW4O6_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mape_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7597 MAP-E CE/BR route.

    Provider ``mape`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mape",
        description=(
            "Drive a first-class RFC 7597 session: bind a loopback Mapping "
            "of Address and Port with Encapsulation (MAP-E) origin, send a "
            "CE with a non-empty mapeid, lockstep a BR that carries the "
            "stored mapedigest, independently poll the stored mapedigest "
            "on a later client socket, and read the sealed mapedigest. "
            "MAPEID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "ce": {"type": "boolean"},
                "br": {"type": "boolean"},
                "mapedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mapeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MAPE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mapt_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7599 MAP-T DMR/EA route.

    Provider ``mapt`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mapt",
        description=(
            "Drive a first-class RFC 7599 session: bind a loopback Mapping "
            "of Address and Port using Translation (MAP-T) origin, send a "
            "DMR with a non-empty maptid, lockstep an EA that carries the "
            "stored maptdigest, independently poll the stored maptdigest "
            "on a later client socket, and read the sealed maptdigest. "
            "MAPTID-gated exchanges stay sealed as digest-chained "
            "actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dmr": {"type": "boolean"},
                "ea": {"type": "boolean"},
                "maptdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_maptid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MAPT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def s46_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7598 S46 RULE/PORTPARAMS route.

    Provider ``s46`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="s46",
        description=(
            "Drive a first-class RFC 7598 session: bind a loopback DHCPv6 "
            "Options for Configuration of Softwire Address and Port-Mapped "
            "Clients origin, send a RULE with a non-empty s46id, lockstep a "
            "PORTPARAMS that carries the stored s46digest, independently poll "
            "the stored s46digest on a later client socket, and read the "
            "sealed s46digest. S46ID-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "rule": {"type": "boolean"},
                "portparams": {"type": "boolean"},
                "s46digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_s46id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=S46_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ucpe_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8026 UCPE CONTAINER/PROVISION route.

    Provider ``ucpe`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ucpe",
        description=(
            "Drive a first-class RFC 8026 session: bind a loopback Unified "
            "IPv4-in-IPv6 Softwire Customer Premises Equipment origin, send a "
            "CONTAINER with a non-empty ucpeid, lockstep a PROVISION that "
            "carries the stored ucpedigest, independently poll the stored "
            "ucpedigest on a later client socket, and read the sealed "
            "ucpedigest. UCPEID-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "container": {"type": "boolean"},
                "provision": {"type": "boolean"},
                "ucpedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ucpeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=UCPE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def m46_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8114 M46 ASM/SSM route.

    Provider ``m46`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="m46",
        description=(
            "Drive a first-class RFC 8114 session: bind a loopback Delivery "
            "of IPv4 Multicast Services to IPv4 Clients over an IPv6 Multicast "
            "Network origin, send an ASM with a non-empty m46id, lockstep an "
            "SSM that carries the stored m46digest, independently poll the "
            "stored m46digest on a later client socket, and read the sealed "
            "m46digest. M46ID-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "asm": {"type": "boolean"},
                "ssm": {"type": "boolean"},
                "m46digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_m46id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=M46_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def prefix64_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8115 PREFIX64 PREFIX/EMBED route.

    Provider ``prefix64`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="prefix64",
        description=(
            "Drive a first-class RFC 8115 session: bind a loopback DHCPv6 "
            "Option for IPv4-Embedded Multicast and Unicast IPv6 Prefixes "
            "origin, send a PREFIX with a non-empty prefix64id, lockstep an "
            "EMBED that carries the stored prefix64digest, independently poll "
            "the stored prefix64digest on a later client socket, and read the "
            "sealed prefix64digest. PREFIX64ID-gated exchanges stay sealed as "
            "digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "prefix": {"type": "boolean"},
                "embed": {"type": "boolean"},
                "prefix64digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_prefix64id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PREFIX64_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def siit_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7915 SIIT TRANSLATE/ICMP route.

    Provider ``siit`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="siit",
        description=(
            "Drive a first-class RFC 7915 session: bind a loopback IP/ICMP "
            "Translation Algorithm origin, send a TRANSLATE with a non-empty "
            "siitid, lockstep an ICMP that carries the stored siitdigest, "
            "independently poll the stored siitdigest on a later client socket, "
            "and read the sealed siitdigest. SIITID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "translate": {"type": "boolean"},
                "icmp": {"type": "boolean"},
                "siitdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_siitid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIIT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def eam_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7757 EAM EXPLICIT/MAPPING route.

    Provider ``eam`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="eam",
        description=(
            "Drive a first-class RFC 7757 session: bind a loopback Explicit "
            "Address Mappings origin, send an EXPLICIT with a non-empty "
            "eamid, lockstep a MAPPING that carries the stored eamdigest, "
            "independently poll the stored eamdigest on a later client socket, "
            "and read the sealed eamdigest. EAMID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "explicit": {"type": "boolean"},
                "mapping": {"type": "boolean"},
                "eamdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_eamid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EAM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )




def siitdc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7755 SIIT-DC PREFIX/DC route.

    Provider ``siitdc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="siitdc",
        description=(
            "Drive a first-class RFC 7755 session: bind a loopback SIIT-DC "
            "Stateless IP/ICMP Translation origin, send a PREFIX with a non-empty "
            "siitdcid, lockstep a DC that carries the stored siitdcdigest, "
            "independently poll the stored siitdcdigest on a later client socket, "
            "and read the sealed siitdcdigest. SIITDCID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "prefix": {"type": "boolean"},
                "dc": {"type": "boolean"},
                "siitdcdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_siitdcid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIITDC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def siitdtm_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7756 SIIT-DTM DTM/MODE route.

    Provider ``siitdtm`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="siitdtm",
        description=(
            "Drive a first-class RFC 7756 session: bind a loopback SIIT-DC "
            "Dual Translation Mode origin, send a DTM with a non-empty "
            "siitdtmid, lockstep a MODE that carries the stored siitdtmdigest, "
            "independently poll the stored siitdtmdigest on a later client socket, "
            "and read the sealed siitdtmdigest. SIITDTMID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dtm": {"type": "boolean"},
                "mode": {"type": "boolean"},
                "siitdtmdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_siitdtmid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIITDTM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def v4embed_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6052 IPv4-embedded IPv6 WKP/NSP route.

    Provider ``v4embed`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="v4embed",
        description=(
            "Drive a first-class RFC 6052 session: bind a loopback IPv6 "
            "Addressing of IPv4/IPv6 Translators origin, send a WKP with a non-empty "
            "v4embedid, lockstep a NSP that carries the stored v4embeddigest, "
            "independently poll the stored v4embeddigest on a later client socket, "
            "and read the sealed v4embeddigest. V4EMBEDID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "wkp": {"type": "boolean"},
                "nsp": {"type": "boolean"},
                "v4embeddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_v4embedid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=V4EMBED_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def luprefix_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8215 Local-Use Prefix LUP/NSL route.

    Provider ``luprefix`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="luprefix",
        description=(
            "Drive a first-class RFC 8215 session: bind a loopback Local-Use "
            "IPv4/IPv6 Translation Prefix origin, send a LUP with a non-empty "
            "luprefixid, lockstep a NSL that carries the stored luprefixdigest, "
            "independently poll the stored luprefixdigest on a later client socket, "
            "and read the sealed luprefixdigest. LUPREFIXID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "lup": {"type": "boolean"},
                "nsl": {"type": "boolean"},
                "luprefixdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_luprefixid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LUPREFIX_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def sixrd_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5969 IPv6 Rapid Deployment 6RD/DELEG route.

    Provider ``sixrd`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sixrd",
        description=(
            "Drive a first-class RFC 5969 session: bind a loopback IPv6 Rapid "
            "Deployment on IPv4 Infrastructures origin, send a 6RD with a non-empty "
            "sixrdid, lockstep a DELEG that carries the stored sixrddigest, "
            "independently poll the stored sixrddigest on a later client socket, "
            "and read the sealed sixrddigest. SIXRDID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "6rd": {"type": "boolean"},
                "deleg": {"type": "boolean"},
                "sixrddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sixrdid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIXRD_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def sixto4_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3056 Connection of IPv6 Domains via IPv4 Clouds 6TO4/BORDER route.

    Provider ``sixto4`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sixto4",
        description=(
            "Drive a first-class RFC 3056 session: bind a loopback Connection of IPv6 "
            "Domains via IPv4 Clouds origin, send a 6TO4 with a non-empty "
            "sixto4id, lockstep a BORDER that carries the stored sixto4digest, "
            "independently poll the stored sixto4digest on a later client socket, "
            "and read the sealed sixto4digest. SIXTO4ID-gated exchanges stay sealed "
            "as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "6to4": {"type": "boolean"},
                "border": {"type": "boolean"},
                "sixto4digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sixto4id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIXTO4_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def teredo_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4380 Teredo Tunneling IPv6 over UDP through NAT BUBBLE/QUAL route.

    Provider ``teredo`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="teredo",
        description=(
            "Drive a first-class RFC 4380 session: bind a loopback Teredo Tunneling "
            "IPv6 over UDP through Network Address Translations origin, send a BUBBLE "
            "with a non-empty teredoid, lockstep a QUAL that carries the stored "
            "teredodigest, independently poll the stored teredodigest on a later "
            "client socket, and read the sealed teredodigest. TEREDOID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "bubble": {"type": "boolean"},
                "qual": {"type": "boolean"},
                "teredodigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_teredoid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TEREDO_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )




def isatap_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5214 Intra-Site Automatic Tunnel Addressing Protocol ISATAP/PRL route.

    Provider ``isatap`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="isatap",
        description=(
            "Drive a first-class RFC 5214 session: bind a loopback Intra-Site Automatic "
            "Tunnel Addressing Protocol origin, send an ISATAP "
            "with a non-empty isatapid, lockstep a PRL that carries the stored "
            "isatapdigest, independently poll the stored isatapdigest on a later "
            "client socket, and read the sealed isatapdigest. ISATAPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "isatap": {"type": "boolean"},
                "prl": {"type": "boolean"},
                "isatapdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_isatapid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ISATAP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def sixover4_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2529 Transmission of IPv6 over IPv4 Domains without Explicit Tunnels 6OVER4/MCAST route.

    Provider ``sixover4`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sixover4",
        description=(
            "Drive a first-class RFC 2529 session: bind a loopback Transmission of IPv6 over IPv4 "
            "Domains without Explicit Tunnels origin, send a 6OVER4 "
            "with a non-empty sixover4id, lockstep a MCAST that carries the stored "
            "sixover4digest, independently poll the stored sixover4digest on a later "
            "client socket, and read the sealed sixover4digest. SIXOVER4ID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "sixover4": {"type": "boolean"},
                "mcast": {"type": "boolean"},
                "sixover4digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sixover4id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIXOVER4_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )




def sixin4_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4213 Basic Transition Mechanisms for IPv6 Hosts and Routers 6IN4/CONFIG route.

    Provider ``sixin4`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="sixin4",
        description=(
            "Drive a first-class RFC 4213 session: bind a loopback Basic Transition Mechanisms for IPv6 "
            "Hosts and Routers origin, send a 6IN4 "
            "with a non-empty sixin4id, lockstep a CONFIG that carries the stored "
            "sixin4digest, independently poll the stored sixin4digest on a later "
            "client socket, and read the sealed sixin4digest. SIXIN4ID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "sixin4": {"type": "boolean"},
                "config": {"type": "boolean"},
                "sixin4digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_sixin4id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SIXIN4_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def tsp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5572 IPv6 Tunnel Broker with the Tunnel Setup Protocol TSP/SETUP route.

    Provider ``tsp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="tsp",
        description=(
            "Drive a first-class RFC 5572 session: bind a loopback IPv6 Tunnel Broker with the Tunnel "
            "Setup Protocol origin, send a TSP "
            "with a non-empty tspid, lockstep a SETUP that carries the stored "
            "tspdigest, independently poll the stored tspdigest on a later "
            "client socket, and read the sealed tspdigest. TSPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "tsp": {"type": "boolean"},
                "setup": {"type": "boolean"},
                "tspdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_tspid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=TSP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def l2tp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5571 Softwire Hub and Spoke L2TP/SPOKE route.

    Provider ``l2tp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="l2tp",
        description=(
            "Drive a first-class RFC 5571 session: bind a loopback Softwire Hub and Spoke "
            "Deployment Framework with Layer Two Tunneling Protocol version 2 origin, send a L2TP "
            "with a non-empty l2tpid, lockstep a SPOKE that carries the stored "
            "l2tpdigest, independently poll the stored l2tpdigest on a later "
            "client socket, and read the sealed l2tpdigest. L2TPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "l2tp": {"type": "boolean"},
                "spoke": {"type": "boolean"},
                "l2tpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_l2tpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=L2TP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mesh_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5565 Softwire Mesh Framework MESH/PEER route.

    Provider ``mesh`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mesh",
        description=(
            "Drive a first-class RFC 5565 session: bind a loopback Softwire Mesh "
            "Framework origin, send a MESH "
            "with a non-empty meshid, lockstep a PEER that carries the stored "
            "meshdigest, independently poll the stored meshdigest on a later "
            "client socket, and read the sealed meshdigest. MESHID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "mesh": {"type": "boolean"},
                "peer": {"type": "boolean"},
                "meshdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_meshid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MESH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def encap_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5512 BGP Encapsulation Subsequent Address Family Identifier ENCAP/SAFI route.

    Provider ``encap`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="encap",
        description=(
            "Drive a first-class RFC 5512 session: bind a loopback BGP Encapsulation Subsequent Address "
            "Family Identifier origin, send an ENCAP "
            "with a non-empty encapid, lockstep a SAFI that carries the stored "
            "encapdigest, independently poll the stored encapdigest on a later "
            "client socket, and read the sealed encapdigest. ENCAPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "encap": {"type": "boolean"},
                "safi": {"type": "boolean"},
                "encapdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_encapid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ENCAP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mpbgp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4760 Multiprotocol Extensions for BGP-4 REACH/UNREACH route.

    Provider ``mpbgp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mpbgp",
        description=(
            "Drive a first-class RFC 4760 session: bind a loopback Multiprotocol Extensions for BGP-4 "
            "origin, send a REACH "
            "with a non-empty mpbgpid, lockstep an UNREACH that carries the stored "
            "mpbgpdigest, independently poll the stored mpbgpdigest on a later "
            "client socket, and read the sealed mpbgpdigest. MPBGPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "mpbgp": {"type": "boolean"},
                "unreach": {"type": "boolean"},
                "mpbgpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mpbgpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MPBGP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def bgp4_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4271 A Border Gateway Protocol 4 BGP-4 OPEN/UPDATE route.

    Provider ``bgp4`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="bgp4",
        description=(
            "Drive a first-class RFC 4271 session: bind a loopback Border Gateway Protocol 4 "
            "origin, send an OPEN "
            "with a non-empty bgp4id, lockstep an UPDATE that carries the stored "
            "bgp4digest, independently poll the stored bgp4digest on a later "
            "client socket, and read the sealed bgp4digest. BGP4ID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "bgp4": {"type": "boolean"},
                "update": {"type": "boolean"},
                "bgp4digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_bgp4id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BGP4_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def rtrefresh_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 2918 Route Refresh Capability for BGP-4 REQUEST/REFRESH route.

    Provider ``rtrefresh`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="rtrefresh",
        description=(
            "Drive a first-class RFC 2918 session: bind a loopback Route Refresh "
            "origin, send a REQUEST "
            "with a non-empty rtrefreshid, lockstep a REFRESH that carries the stored "
            "rtrefreshdigest, independently poll the stored rtrefreshdigest on a later "
            "client socket, and read the sealed rtrefreshdigest. RTREFRESHID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "rtrefresh": {"type": "boolean"},
                "refresh": {"type": "boolean"},
                "rtrefreshdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_rtrefreshid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RTREFRESH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def bgpcomm_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 1997 BGP Communities Attribute COMM/ATTR route.

    Provider ``bgpcomm`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="bgpcomm",
        description=(
            "Drive a first-class RFC 1997 session: bind a loopback BGP Communities "
            "origin, send a COMM "
            "with a non-empty bgpcommid, lockstep an ATTR that carries the stored "
            "bgpcommdigest, independently poll the stored bgpcommdigest on a later "
            "client socket, and read the sealed bgpcommdigest. BGPCOMMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "bgpcomm": {"type": "boolean"},
                "attr": {"type": "boolean"},
                "bgpcommdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_bgpcommid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BGPCOMM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def extcomm_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4360 BGP Extended Communities Attribute EXT/TYPE route.

    Provider ``extcomm`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="extcomm",
        description=(
            "Drive a first-class RFC 4360 session: bind a loopback BGP Extended Communities "
            "origin, send a EXT "
            "with a non-empty extcommid, lockstep a TYPE that carries the stored "
            "extcommdigest, independently poll the stored extcommdigest on a later "
            "client socket, and read the sealed extcommdigest. EXTCOMMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "extcomm": {"type": "boolean"},
                "type": {"type": "boolean"},
                "extcommdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_extcommid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EXTCOMM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def largecomm_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8092 BGP Large Communities Attribute LARGE/PART route.

    Provider ``largecomm`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="largecomm",
        description=(
            "Drive a first-class RFC 8092 session: bind a loopback BGP Large Communities "
            "origin, send a LARGE "
            "with a non-empty largecommid, lockstep a PART that carries the stored "
            "largecommdigest, independently poll the stored largecommdigest on a later "
            "client socket, and read the sealed largecommdigest. LARGECOMMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "largecomm": {"type": "boolean"},
                "part": {"type": "boolean"},
                "largecommdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_largecommid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LARGECOMM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def bgpsec_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8205 BGPsec Protocol SIGN/PATH route.

    Provider ``bgpsec`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="bgpsec",
        description=(
            "Drive a first-class RFC 8205 session: bind a loopback BGPsec Protocol "
            "origin, send a SIGN "
            "with a non-empty bgpsecid, lockstep a PATH that carries the stored "
            "bgpsecdigest, independently poll the stored bgpsecdigest on a later "
            "client socket, and read the sealed bgpsecdigest. BGPSECID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "bgpsec": {"type": "boolean"},
                "path": {"type": "boolean"},
                "bgpsecdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_bgpsecid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BGPSEC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def rtr_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8210 RPKI to Router Protocol SERIAL/RESET route.

    Provider ``rtr`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="rtr",
        description=(
            "Drive a first-class RFC 8210 session: bind a loopback RPKI to Router Protocol "
            "origin, send a SERIAL "
            "with a non-empty rtrid, lockstep a RESET that carries the stored "
            "rtrdigest, independently poll the stored rtrdigest on a later "
            "client socket, and read the sealed rtrdigest. RTRID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "rtr": {"type": "boolean"},
                "reset": {"type": "boolean"},
                "rtrdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_rtrid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RTR_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ebgp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8212 Default EBGP Route Propagation DEF/PROP route.

    Provider ``ebgp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ebgp",
        description=(
            "Drive a first-class RFC 8212 session: bind a loopback Default EBGP Route Propagation "
            "origin, send a DEF "
            "with a non-empty ebgpid, lockstep a PROP that carries the stored "
            "ebgpdigest, independently poll the stored ebgpdigest on a later "
            "client socket, and read the sealed ebgpdigest. EBGPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "ebgp": {"type": "boolean"},
                "prop": {"type": "boolean"},
                "ebgpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ebgpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EBGP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def evpn_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8214 Virtual Private Wire Service Support in Ethernet VPN AD/VPWS route.

    Provider ``evpn`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="evpn",
        description=(
            "Drive a first-class RFC 8214 session: bind a loopback Virtual Private Wire Service Support in Ethernet VPN "
            "origin, send a AD "
            "with a non-empty evpnid, lockstep a VPWS that carries the stored "
            "evpndigest, independently poll the stored evpndigest on a later "
            "client socket, and read the sealed evpndigest. EVPNID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "evpn": {"type": "boolean"},
                "vpws": {"type": "boolean"},
                "evpndigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_evpnid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EVPN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def etree_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8317 Ethernet-Tree (E-Tree) Support in Ethernet VPN ROOT/LEAF route.

    Provider ``etree`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="etree",
        description=(
            "Drive a first-class RFC 8317 session: bind a loopback Ethernet-Tree (E-Tree) Support in Ethernet VPN "
            "origin, send a ROOT "
            "with a non-empty etreeid, lockstep a LEAF that carries the stored "
            "etreedigest, independently poll the stored etreedigest on a later "
            "client socket, and read the sealed etreedigest. ETREEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "etree": {"type": "boolean"},
                "leaf": {"type": "boolean"},
                "etreedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_etreeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ETREE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def nvo_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8365 Network Virtualization Overlay NVE/VNI route.

    Provider ``nvo`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="nvo",
        description=(
            "Drive a first-class RFC 8365 session: bind a loopback Network Virtualization Overlay "
            "origin, send a NVE "
            "with a non-empty nvoid, lockstep a VNI that carries the stored "
            "nvodigest, independently poll the stored nvodigest on a later "
            "client socket, and read the sealed nvodigest. NVOID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "nvo": {"type": "boolean"},
                "vni": {"type": "boolean"},
                "nvodigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_nvoid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=NVO_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def dfe_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 8584 Ethernet VPN Designated Forwarder Election DF/NDF route.

    Provider ``dfe`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dfe",
        description=(
            "Drive a first-class RFC 8584 session: bind a loopback Ethernet VPN Designated Forwarder Election "
            "origin, send a DF "
            "with a non-empty dfeid, lockstep a NDF that carries the stored "
            "dfedigest, independently poll the stored dfedigest on a later "
            "client socket, and read the sealed dfedigest. DFEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dfe": {"type": "boolean"},
                "ndf": {"type": "boolean"},
                "dfedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dfeid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DFE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def irb_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9135 Integrated Routing and Bridging in Ethernet VPN IRB/L3 route.

    Provider ``irb`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="irb",
        description=(
            "Drive a first-class RFC 9135 session: bind a loopback Integrated Routing and Bridging in Ethernet VPN "
            "origin, send a IRB "
            "with a non-empty irbid, lockstep a L3 that carries the stored "
            "irbdigest, independently poll the stored irbdigest on a later "
            "client socket, and read the sealed irbdigest. IRBID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "irb": {"type": "boolean"},
                "l3": {"type": "boolean"},
                "irbdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_irbid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IRB_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ippfx_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9136 IP Prefix Advertisement in Ethernet VPN PREFIX/IP route.

    Provider ``ippfx`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ippfx",
        description=(
            "Drive a first-class RFC 9136 session: bind a loopback IP Prefix Advertisement in Ethernet VPN "
            "origin, send a PREFIX "
            "with a non-empty ippfxid, lockstep a IP that carries the stored "
            "ippfxdigest, independently poll the stored ippfxdigest on a later "
            "client socket, and read the sealed ippfxdigest. IPPFXID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "ippfx": {"type": "boolean"},
                "ip": {"type": "boolean"},
                "ippfxdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ippfxid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IPPFX_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def proxynd_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9161 Operational Aspects of Proxy-ARP/ND in Ethernet VPN PROXY/ND route.

    Provider ``proxynd`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="proxynd",
        description=(
            "Drive a first-class RFC 9161 session: bind a loopback Operational Aspects of Proxy-ARP/ND in Ethernet VPN "
            "origin, send a PROXY "
            "with a non-empty proxyndid, lockstep a ND that carries the stored "
            "proxynddigest, independently poll the stored proxynddigest on a later "
            "client socket, and read the sealed proxynddigest. PROXYNDID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "proxynd": {"type": "boolean"},
                "nd": {"type": "boolean"},
                "proxynddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_proxyndid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PROXYND_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def imlproxy_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9251 IGMP and MLD Proxies for Ethernet VPN IGMP/MLD route.

    Provider ``imlproxy`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="imlproxy",
        description=(
            "Drive a first-class RFC 9251 session: bind a loopback IGMP and MLD Proxies for Ethernet VPN "
            "origin, send a IGMP "
            "with a non-empty imlproxyid, lockstep a MLD that carries the stored "
            "imlproxydigest, independently poll the stored imlproxydigest on a later "
            "client socket, and read the sealed imlproxydigest. IMLPROXYID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "imlproxy": {"type": "boolean"},
                "mld": {"type": "boolean"},
                "imlproxydigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_imlproxyid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IMLPROXY_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def evpnbum_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9572 Updates to EVPN BUM Procedures SMET/IMET route.

    Provider ``evpnbum`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="evpnbum",
        description=(
            "Drive a first-class RFC 9572 session: bind a loopback Updates to EVPN BUM Procedures "
            "origin, send a SMET "
            "with a non-empty evpnbumid, lockstep a IMET that carries the stored "
            "evpnbumdigest, independently poll the stored evpnbumdigest on a later "
            "client socket, and read the sealed evpnbumdigest. EVPNBUMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "evpnbum": {"type": "boolean"},
                "imet": {"type": "boolean"},
                "evpnbumdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_evpnbumid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EVPNBUM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def fxc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9625 EVPN VPWS Flexible Cross-Connect FXC/VLAN route.

    Provider ``fxc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="fxc",
        description=(
            "Drive a first-class RFC 9625 session: bind a loopback EVPN VPWS Flexible Cross-Connect "
            "origin, send a FXC "
            "with a non-empty fxcid, lockstep a VLAN that carries the stored "
            "fxcdigest, independently poll the stored fxcdigest on a later "
            "client socket, and read the sealed fxcdigest. FXCID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "fxc": {"type": "boolean"},
                "vlan": {"type": "boolean"},
                "fxcdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_fxcid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=FXC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def dfrec_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9722 Fast Recovery for EVPN Designated Forwarder Election DFREC/FAST route.

    Provider ``dfrec`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dfrec",
        description=(
            "Drive a first-class RFC 9722 session: bind a loopback Fast Recovery for EVPN Designated Forwarder Election "
            "origin, send a DFREC "
            "with a non-empty dfrecid, lockstep a FAST that carries the stored "
            "dfrecdigest, independently poll the stored dfrecdigest on a later "
            "client socket, and read the sealed dfrecdigest. DFRECID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "dfrec": {"type": "boolean"},
                "fast": {"type": "boolean"},
                "dfrecdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dfrecid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DFREC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def msred_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9856 Multicast Source Redundancy in EVPNs WARM/HOT route.

    Provider ``msred`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="msred",
        description=(
            "Drive a first-class RFC 9856 session: bind a loopback Multicast Source Redundancy in EVPNs "
            "origin, send a WARM "
            "with a non-empty msredid, lockstep a HOT that carries the stored "
            "msreddigest, independently poll the stored msreddigest on a later "
            "client socket, and read the sealed msreddigest. MSREDID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "msred": {"type": "boolean"},
                "hot": {"type": "boolean"},
                "msreddigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_msredid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MSRED_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def p2mpir_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 10018 Multicast and Ethernet VPN with Segment Routing P2MP/IR route.

    Provider ``p2mpir`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="p2mpir",
        description=(
            "Drive a first-class RFC 10018 session: bind a loopback Multicast and Ethernet VPN with Segment Routing "
            "origin, send a P2MP "
            "with a non-empty p2mpirid, lockstep an IR that carries the stored "
            "p2mpirdigest, independently poll the stored p2mpirdigest on a later "
            "client socket, and read the sealed p2mpirdigest. P2MPIRID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "p2mpir": {"type": "boolean"},
                "ir": {"type": "boolean"},
                "p2mpirdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_p2mpirid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=P2MPIR_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def oir_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9574 Optimized Ingress Replication for EVPN OIR/BUM route.

    Provider ``oir`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="oir",
        description=(
            "Drive a first-class RFC 9574 session: bind a loopback Optimized Ingress Replication for EVPN "
            "origin, send an OIR "
            "with a non-empty oirid, lockstep a BUM that carries the stored "
            "oirdigest, independently poll the stored oirdigest on a later "
            "client socket, and read the sealed oirdigest. OIRID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "oir": {"type": "boolean"},
                "bum": {"type": "boolean"},
                "oirdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_oirid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OIR_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def iesi_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 9014 Interconnect Solution for Ethernet VPN Overlay Networks IESI/GW route.

    Provider ``iesi`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="iesi",
        description=(
            "Drive a first-class RFC 9014 session: bind a loopback Interconnect Solution for Ethernet VPN Overlay Networks "
            "origin, send an IESI "
            "with a non-empty iesiid, lockstep a GW that carries the stored "
            "iesidigest, independently poll the stored iesidigest on a later "
            "client socket, and read the sealed iesidigest. IESIID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "iesi": {"type": "boolean"},
                "gw": {"type": "boolean"},
                "iesidigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_iesiid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=IESI_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pbb_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7623 Provider Backbone Bridging Combined with Ethernet VPN PBB/BMAC route.

    Provider ``pbb`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pbb",
        description=(
            "Drive a first-class RFC 7623 session: bind a loopback Provider Backbone Bridging Combined with Ethernet VPN "
            "origin, send a PBB "
            "with a non-empty pbbid, lockstep a BMAC that carries the stored "
            "pbbdigest, independently poll the stored pbbdigest on a later "
            "client socket, and read the sealed pbbdigest. PBBID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "pbb": {"type": "boolean"},
                "bmac": {"type": "boolean"},
                "pbbdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pbbid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PBB_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def macip_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7432 BGP MPLS-Based Ethernet VPN MAC/IP route.

    Provider ``macip`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="macip",
        description=(
            "Drive a first-class RFC 7432 session: bind a loopback BGP MPLS-Based Ethernet VPN "
            "origin, send a MAC "
            "with a non-empty macipid, lockstep an IP that carries the stored "
            "macipdigest, independently poll the stored macipdigest on a later "
            "client socket, and read the sealed macipdigest. MACIPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "mac": {"type": "boolean"},
                "ip": {"type": "boolean"},
                "macipdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_macipid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MACIP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def evpnreq_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 7209 Requirements for Ethernet VPN REQ/AA route.

    Provider ``evpnreq`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="evpnreq",
        description=(
            "Drive a first-class RFC 7209 session: bind a loopback Requirements for Ethernet VPN "
            "origin, send a REQ "
            "with a non-empty evpnreqid, lockstep an AA that carries the stored "
            "evpnreqdigest, independently poll the stored evpnreqdigest on a later "
            "client socket, and read the sealed evpnreqdigest. EVPNREQID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "req": {"type": "boolean"},
                "aa": {"type": "boolean"},
                "evpnreqdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_evpnreqid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EVPNREQ_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def vpls_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4761 Virtual Private LAN Service Using BGP VE/NLRI route.

    Provider ``vpls`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="vpls",
        description=(
            "Drive a first-class RFC 4761 session: bind a loopback Virtual Private LAN Service Using BGP "
            "origin, send a VE "
            "with a non-empty vplsid, lockstep an NLRI that carries the stored "
            "vplsdigest, independently poll the stored vplsdigest on a later "
            "client socket, and read the sealed vplsdigest. VPLSID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "ve": {"type": "boolean"},
                "nlri": {"type": "boolean"},
                "vplsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_vplsid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=VPLS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def ldpsig_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4762 Virtual Private LAN Service Using LDP PW/FEC route.

    Provider ``ldpsig`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ldpsig",
        description=(
            "Drive a first-class RFC 4762 session: bind a loopback Virtual Private LAN Service Using LDP "
            "origin, send a PW "
            "with a non-empty ldpsigid, lockstep an FEC that carries the stored "
            "ldpsigdigest, independently poll the stored ldpsigdigest on a later "
            "client socket, and read the sealed ldpsigdigest. LDPSIGID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "pw": {"type": "boolean"},
                "fec": {"type": "boolean"},
                "ldpsigdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ldpsigid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LDPSIG_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pwldp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4447 Pseudowire Setup and Maintenance Using LDP LABEL/STATUS route.

    Provider ``pwldp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pwldp",
        description=(
            "Drive a first-class RFC 4447 session: bind a loopback Pseudowire Setup and Maintenance Using LDP "
            "origin, send a LABEL "
            "with a non-empty pwldpid, lockstep a STATUS that carries the stored "
            "pwldpdigest, independently poll the stored pwldpdigest on a later "
            "client socket, and read the sealed pwldpdigest. PWLDPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "label": {"type": "boolean"},
                "status": {"type": "boolean"},
                "pwldpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pwldpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PWLDP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pwe3_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3985 Pseudo Wire Emulation Edge-to-Edge (PWE3) Architecture PSN/NSP route.

    Provider ``pwe3`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pwe3",
        description=(
            "Drive a first-class RFC 3985 session: bind a loopback Pseudo Wire Emulation Edge-to-Edge (PWE3) Architecture "
            "origin, send a PSN "
            "with a non-empty pwe3id, lockstep an NSP that carries the stored "
            "pwe3digest, independently poll the stored pwe3digest on a later "
            "client socket, and read the sealed pwe3digest. PWE3ID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "psn": {"type": "boolean"},
                "nsp": {"type": "boolean"},
                "pwe3digest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pwe3id": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PWE3_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pwreq_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3916 Requirements for Pseudo-Wire Emulation Edge-to-Edge NATIVE/PW route.

    Provider ``pwreq`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pwreq",
        description=(
            "Drive a first-class RFC 3916 session: bind a loopback Requirements for Pseudo-Wire Emulation Edge-to-Edge "
            "origin, send a NATIVE "
            "with a non-empty pwreqid, lockstep a PW that carries the stored "
            "pwreqdigest, independently poll the stored pwreqdigest on a later "
            "client socket, and read the sealed pwreqdigest. PWREQID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "native": {"type": "boolean"},
                "pw": {"type": "boolean"},
                "pwreqdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pwreqid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PWREQ_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mplsarch_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3031 Multiprotocol Label Switching Architecture FEC/NHLFE route.

    Provider ``mplsarch`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mplsarch",
        description=(
            "Drive a first-class RFC 3031 session: bind a loopback Multiprotocol Label Switching Architecture "
            "origin, send a FEC "
            "with a non-empty mplsid, lockstep an NHLFE that carries the stored "
            "mplsdigest, independently poll the stored mplsdigest on a later "
            "client socket, and read the sealed mplsdigest. MPLSID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "fec": {"type": "boolean"},
                "nhlfe": {"type": "boolean"},
                "mplsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mplsid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MPLSARCH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mplslse_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3032 MPLS Label Stack Encoding LABEL/STACK route.

    Provider ``mplslse`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mplslse",
        description=(
            "Drive a first-class RFC 3032 session: bind a loopback MPLS Label Stack Encoding "
            "origin, send a LABEL "
            "with a non-empty lseid, lockstep a STACK that carries the stored "
            "lsedigest, independently poll the stored lsedigest on a later "
            "client socket, and read the sealed lsedigest. LSEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "label": {"type": "boolean"},
                "stack": {"type": "boolean"},
                "lsedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lseid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MPLSLSE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )




def rsvpte_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3209 RSVP-TE PATH/RESV route.

    Provider ``rsvpte`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="rsvpte",
        description=(
            "Drive a first-class RFC 3209 session: bind a loopback RSVP-TE "
            "origin, send a PATH "
            "with a non-empty rsvpteid, lockstep a RESV that carries the stored "
            "rsvptedigest, independently poll the stored rsvptedigest on a later "
            "client socket, and read the sealed rsvptedigest. RSVPTEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "path": {"type": "boolean"},
                "resv": {"type": "boolean"},
                "rsvptedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_rsvpteid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=RSVPTE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def gmpls_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 3473 GMPLS RSVP-TE NOTIFY/RESVCONF route.

    Provider ``gmpls`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="gmpls",
        description=(
            "Drive a first-class RFC 3473 session: bind a loopback GMPLS RSVP-TE "
            "origin, send a NOTIFY "
            "with a non-empty gmplsid, lockstep a RESVCONF that carries the stored "
            "gmplsdigest, independently poll the stored gmplsdigest on a later "
            "client socket, and read the sealed gmplsdigest. GMPLSID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "notify": {"type": "boolean"},
                "resvconf": {"type": "boolean"},
                "gmplsdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_gmplsid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GMPLS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lmp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4204 LMP CONFIG/HELLO route.

    Provider ``lmp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lmp",
        description=(
            "Drive a first-class RFC 4204 session: bind a loopback LMP "
            "origin, send a CONFIG "
            "with a non-empty lmpid, lockstep a HELLO that carries the stored "
            "lmpdigest, independently poll the stored lmpdigest on a later "
            "client socket, and read the sealed lmpdigest. LMPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "config": {"type": "boolean"},
                "hello": {"type": "boolean"},
                "lmpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lmpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lsphier_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4206 LSP HIERARCHY FA/HIERARCHY route.

    Provider ``lsphier`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lsphier",
        description=(
            "Drive a first-class RFC 4206 session: bind a loopback LSP Hierarchy "
            "origin, send a FA "
            "with a non-empty lsphierid, lockstep a HIERARCHY that carries the stored "
            "lsphierdigest, independently poll the stored lsphierdigest on a later "
            "client socket, and read the sealed lsphierdigest. LSPHIERID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "fa": {"type": "boolean"},
                "hierarchy": {"type": "boolean"},
                "lsphierdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lsphierid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LSPHIER_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def guni_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4208 GMPLS UNI UNIC/UNIN route.

    Provider ``guni`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="guni",
        description=(
            "Drive a first-class RFC 4208 session: bind a loopback GMPLS UNI "
            "origin, send a UNIC "
            "with a non-empty guniid, lockstep a UNIN that carries the stored "
            "gunidigest, independently poll the stored gunidigest on a later "
            "client socket, and read the sealed gunidigest. GUNIID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "unic": {"type": "boolean"},
                "unin": {"type": "boolean"},
                "gunidigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_guniid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GUNI_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lwdm_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4209 LMP-WDM VERIFY/TRACE route.

    Provider ``lwdm`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lwdm",
        description=(
            "Drive a first-class RFC 4209 session: bind a loopback LMP-WDM "
            "origin, send a VERIFY "
            "with a non-empty lwdmid, lockstep a TRACE that carries the stored "
            "lwdmdigest, independently poll the stored lwdmdigest on a later "
            "client socket, and read the sealed lwdmdigest. LWDMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "verify": {"type": "boolean"},
                "trace": {"type": "boolean"},
                "lwdmdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lwdmid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LWDM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def otn_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4328 GMPLS OTN OTU/ODU route.

    Provider ``otn`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="otn",
        description=(
            "Drive a first-class RFC 4328 session: bind a loopback GMPLS OTN "
            "origin, send a OTU "
            "with a non-empty otnid, lockstep a ODU that carries the stored "
            "otndigest, independently poll the stored otndigest on a later "
            "client socket, and read the sealed otndigest. OTNID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "otu": {"type": "boolean"},
                "odu": {"type": "boolean"},
                "otndigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_otnid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OTN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def ason_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4397 GMPLS ASON CALL/CONN route.

    Provider ``ason`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ason",
        description=(
            "Drive a first-class RFC 4397 session: bind a loopback GMPLS ASON "
            "origin, send a CALL "
            "with a non-empty asonid, lockstep a CONN that carries the stored "
            "asondigest, independently poll the stored asondigest on a later "
            "client socket, and read the sealed asondigest. ASONID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "call": {"type": "boolean"},
                "conn": {"type": "boolean"},
                "asondigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_asonid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ASON_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def grec_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4426 GMPLS Recovery NOTIFY/RESTORE route.

    Provider ``grec`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="grec",
        description=(
            "Drive a first-class RFC 4426 session: bind a loopback GMPLS Recovery "
            "origin, send a NOTIFY "
            "with a non-empty grecid, lockstep a RESTORE that carries the stored "
            "grecdigest, independently poll the stored grecdigest on a later "
            "client socket, and read the sealed grecdigest. GRECID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "notify": {"type": "boolean"},
                "restore": {"type": "boolean"},
                "grecdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_grecid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GREC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def e2erec_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4872 GMPLS End-to-End Recovery PROTECT/SWITCH route.

    Provider ``e2erec`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="e2erec",
        description=(
            "Drive a first-class RFC 4872 session: bind a loopback GMPLS End-to-End "
            "Recovery origin, send a PROTECT "
            "with a non-empty e2erecid, lockstep a SWITCH that carries the stored "
            "e2erecdigest, independently poll the stored e2erecdigest on a later "
            "client socket, and read the sealed e2erecdigest. E2ERECID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "protect": {"type": "boolean"},
                "switch": {"type": "boolean"},
                "e2erecdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_e2erecid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=E2EREC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def segrec_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4873 GMPLS Segment Recovery SEGMENT/RECOVER route.

    Provider ``segrec`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="segrec",
        description=(
            "Drive a first-class RFC 4873 session: bind a loopback GMPLS Segment "
            "Recovery origin, send a SEGMENT "
            "with a non-empty segrecid, lockstep a RECOVER that carries the stored "
            "segrecdigest, independently poll the stored segrecdigest on a later "
            "client socket, and read the sealed segrecdigest. SEGRECID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "segment": {"type": "boolean"},
                "recover": {"type": "boolean"},
                "segrecdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_segrecid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SEGREC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def exroute_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4874 Exclude Routes EXCLUDE/ROUTE route.

    Provider ``exroute`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="exroute",
        description=(
            "Drive a first-class RFC 4874 session: bind a loopback Exclude "
            "Routes origin, send an EXCLUDE "
            "with a non-empty exrouteid, lockstep a ROUTE that carries the stored "
            "exroutedigest, independently poll the stored exroutedigest on a later "
            "client socket, and read the sealed exroutedigest. EXROUTEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "exclude": {"type": "boolean"},
                "route": {"type": "boolean"},
                "exroutedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_exrouteid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=EXROUTE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def p2mpte_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4875 Point-to-Multipoint TE LSPs P2MP/S2L route.

    Provider ``p2mpte`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="p2mpte",
        description=(
            "Drive a first-class RFC 4875 session: bind a loopback Point-to-Multipoint "
            "TE LSPs origin, send a P2MP "
            "with a non-empty p2mpteid, lockstep an S2L that carries the stored "
            "p2mptedigest, independently poll the stored p2mptedigest on a later "
            "client socket, and read the sealed p2mptedigest. P2MPTEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "p2mp": {"type": "boolean"},
                "s2l": {"type": "boolean"},
                "p2mptedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_p2mpteid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=P2MPTE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def crankback_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 4920 Crankback Signaling CRANK/RETRY route.

    Provider ``crankback`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="crankback",
        description=(
            "Drive a first-class RFC 4920 session: bind a loopback Crankback "
            "Signaling origin, send a CRANK "
            "with a non-empty crankbackid, lockstep a RETRY that carries the stored "
            "crankbackdigest, independently poll the stored crankbackdigest on a later "
            "client socket, and read the sealed crankbackdigest. CRANKBACKID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "crank": {"type": "boolean"},
                "retry": {"type": "boolean"},
                "crankbackdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_crankbackid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=CRANKBACK_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lspstitch_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5150 Label Switched Path Stitching STITCH/JOIN route.

    Provider ``lspstitch`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lspstitch",
        description=(
            "Drive a first-class RFC 5150 session: bind a loopback Label Switched Path "
            "Stitching origin, send a STITCH "
            "with a non-empty lspstitchid, lockstep a JOIN that carries the stored "
            "lspstitchdigest, independently poll the stored lspstitchdigest on a later "
            "client socket, and read the sealed lspstitchdigest. LSPSTITCHID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "stitch": {"type": "boolean"},
                "join": {"type": "boolean"},
                "lspstitchdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lspstitchid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LSPSTITCH_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def interas_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5151 Inter-AS Traffic Engineering CONTIG/NEST route.

    Provider ``interas`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="interas",
        description=(
            "Drive a first-class RFC 5151 session: bind a loopback Inter-AS Traffic "
            "Engineering origin, send a CONTIG "
            "with a non-empty interasid, lockstep a NEST that carries the stored "
            "interasdigest, independently poll the stored interasdigest on a later "
            "client socket, and read the sealed interasdigest. INTERASID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "contig": {"type": "boolean"},
                "nest": {"type": "boolean"},
                "interasdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_interasid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=INTERAS_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def perdom_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5152 Per-Domain Path Computation COMPUTE/DOMAIN route.

    Provider ``perdom`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="perdom",
        description=(
            "Drive a first-class RFC 5152 session: bind a loopback Per-Domain Path "
            "Computation origin, send a COMPUTE "
            "with a non-empty perdomid, lockstep a DOMAIN that carries the stored "
            "perdomdigest, independently poll the stored perdomdigest on a later "
            "client socket, and read the sealed perdomdigest. PERDOMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "compute": {"type": "boolean"},
                "domain": {"type": "boolean"},
                "perdomdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_perdomid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PERDOM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pcep_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5440 Path Computation Element Communication Protocol OPEN/PCREQ route.

    Provider ``pcep`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pcep",
        description=(
            "Drive a first-class RFC 5440 session: bind a loopback Path Computation "
            "Element Communication Protocol origin, send an OPEN "
            "with a non-empty pcepid, lockstep a PCREQ that carries the stored "
            "pcepdigest, independently poll the stored pcepdigest on a later "
            "client socket, and read the sealed pcepdigest. PCEPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "open": {"type": "boolean"},
                "pcreq": {"type": "boolean"},
                "pcepdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pcepid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PCEP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def brpc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5441 Backward-Recursive PCE-Based Computation BRPC/REPLY route.

    Provider ``brpc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="brpc",
        description=(
            "Drive a first-class RFC 5441 session: bind a loopback Backward-Recursive "
            "PCE-Based Computation origin, send a BRPC "
            "with a non-empty brpcid, lockstep a REPLY that carries the stored "
            "brpcdigest, independently poll the stored brpcdigest on a later "
            "client socket, and read the sealed brpcdigest. BRPCID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "brpc": {"type": "boolean"},
                "reply": {"type": "boolean"},
                "brpcdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_brpcid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=BRPC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def dsct_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5455 Diffserv-aware Class-Type Object CLASS/TYPE route.

    Provider ``dsct`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="dsct",
        description=(
            "Drive a first-class RFC 5455 session: bind a loopback Diffserv-aware "
            "Class-Type Object origin, send a CLASS "
            "with a non-empty dsctid, lockstep a TYPE that carries the stored "
            "dsctdigest, independently poll the stored dsctdigest on a later "
            "client socket, and read the sealed dsctdigest. DSCTID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "class": {"type": "boolean"},
                "type": {"type": "boolean"},
                "dsctdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_dsctid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=DSCT_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pathkey_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5520 Path-Key-Based Mechanism PATH/KEY route.

    Provider ``pathkey`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pathkey",
        description=(
            "Drive a first-class RFC 5520 session: bind a loopback Path-Key-Based "
            "Mechanism origin, send a PATH "
            "with a non-empty pathkeyid, lockstep a KEY that carries the stored "
            "pathkeydigest, independently poll the stored pathkeydigest on a later "
            "client socket, and read the sealed pathkeydigest. PATHKEYID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "path": {"type": "boolean"},
                "key": {"type": "boolean"},
                "pathkeydigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pathkeyid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PATHKEY_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pcexcl_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5521 PCE Route Exclusions EXCLUDE/XRO route.

    Provider ``pcexcl`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pcexcl",
        description=(
            "Drive a first-class RFC 5521 session: bind a loopback PCE Route "
            "Exclusions origin, send an EXCLUDE "
            "with a non-empty pcexclid, lockstep an XRO that carries the stored "
            "pcexcldigest, independently poll the stored pcexcldigest on a later "
            "client socket, and read the sealed pcexcldigest. PCEXCLID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "exclude": {"type": "boolean"},
                "xro": {"type": "boolean"},
                "pcexcldigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pcexclid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PCEXCL_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def objfun_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5541 Encoding of Objective Functions OBJ/FUN route.

    Provider ``objfun`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="objfun",
        description=(
            "Drive a first-class RFC 5541 session: bind a loopback Encoding of "
            "Objective Functions origin, send an OBJ "
            "with a non-empty objfunid, lockstep a FUN that carries the stored "
            "objfundest, independently poll the stored objfundest on a later "
            "client socket, and read the sealed objfundest. OBJFUNID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "obj": {"type": "boolean"},
                "fun": {"type": "boolean"},
                "objfundest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_objfunid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=OBJFUN_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def gco_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5557 Global Concurrent Optimization GCO/SVEC route.

    Provider ``gco`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="gco",
        description=(
            "Drive a first-class RFC 5557 session: bind a loopback Global Concurrent "
            "Optimization origin, send a GCO "
            "with a non-empty gcoid, lockstep a SVEC that carries the stored "
            "gcodigest, independently poll the stored gcodigest on a later "
            "client socket, and read the sealed gcodigest. GCOID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "gco": {"type": "boolean"},
                "svec": {"type": "boolean"},
                "gcodigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_gcoid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=GCO_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )




def ilpce_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5623 PCE-Based Inter-Layer MPLS and GMPLS Traffic Engineering VNTM/LAYER route.

    Provider ``ilpce`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="ilpce",
        description=(
            "Drive a first-class RFC 5623 session: bind a loopback PCE-Based Inter-Layer "
            "MPLS and GMPLS Traffic Engineering origin, send a VNTM "
            "with a non-empty ilpceid, lockstep a LAYER that carries the stored "
            "ilpcedigest, independently poll the stored ilpcedigest on a later "
            "client socket, and read the sealed ilpcedigest. ILPCEID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "vntm": {"type": "boolean"},
                "layer": {"type": "boolean"},
                "ilpcedigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_ilpceid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ILPCE_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pcemon_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 5886 A Set of Monitoring Tools for PCE-Based Architecture MON/PCEID route.

    Provider ``pcemon`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pcemon",
        description=(
            "Drive a first-class RFC 5886 session: bind a loopback A Set of Monitoring Tools "
            "for PCE-Based Architecture origin, send a MON "
            "with a non-empty pcemonid, lockstep a PCEID that carries the stored "
            "pcemondigest, independently poll the stored pcemondigest on a later "
            "client socket, and read the sealed pcemondigest. PCEMONID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "mon": {"type": "boolean"},
                "pceid": {"type": "boolean"},
                "pcemondigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pcemonid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PCEMON_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pcepmp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6006 Extensions to PCEP for Point-to-Multipoint TE LSPs P2MP/ENDPOINTS route.

    Provider ``pcepmp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pcepmp",
        description=(
            "Drive a first-class RFC 6006 session: bind a loopback Extensions to PCEP "
            "for Point-to-Multipoint TE LSPs origin, send a P2MP "
            "with a non-empty pcepmpid, lockstep an ENDPOINTS that carries the stored "
            "pcepmpdigest, independently poll the stored pcepmpdigest on a later "
            "client socket, and read the sealed pcepmpdigest. PCEPMPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "p2mp": {"type": "boolean"},
                "endpoints": {"type": "boolean"},
                "pcepmpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pcepmpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PCEPMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def wson_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6163 Framework for GMPLS and PCE Control of Wavelength Switched Optical Networks WSON/RWA route.

    Provider ``wson`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="wson",
        description=(
            "Drive a first-class RFC 6163 session: bind a loopback Framework for GMPLS "
            "and PCE Control of Wavelength Switched Optical Networks origin, send a WSON "
            "with a non-empty wsonid, lockstep an RWA that carries the stored "
            "wsondigest, independently poll the stored wsondigest on a later "
            "client socket, and read the sealed wsondigest. WSONID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "wson": {"type": "boolean"},
                "rwa": {"type": "boolean"},
                "wsondigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_wsonid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=WSON_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lsc_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6205 Generalized Labels for Lambda-Switch-Capable (LSC) Label Switching Routers LSC/LABEL route.

    Provider ``lsc`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lsc",
        description=(
            "Drive a first-class RFC 6205 session: bind a loopback Generalized Labels "
            "for Lambda-Switch-Capable (LSC) Label Switching Routers origin, send a LSC "
            "with a non-empty lscid, lockstep a LABEL that carries the stored "
            "lscdigest, independently poll the stored lscdigest on a later "
            "client socket, and read the sealed lscdigest. LSCID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "lsc": {"type": "boolean"},
                "label": {"type": "boolean"},
                "lscdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lscid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LSC_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def asbw_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6387 GMPLS Asymmetric Bandwidth Bidirectional Label Switched Paths (LSPs) ASYM/BIDIR route.

    Provider ``asbw`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="asbw",
        description=(
            "Drive a first-class RFC 6387 session: bind a loopback GMPLS Asymmetric "
            "Bandwidth Bidirectional Label Switched Paths origin, send an ASYM "
            "with a non-empty asbwid, lockstep a BIDIR that carries the stored "
            "asbwdigest, independently poll the stored asbwdigest on a later "
            "client socket, and read the sealed asbwdigest. ASBWID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "asym": {"type": "boolean"},
                "bidir": {"type": "boolean"},
                "asbwdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_asbwid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=ASBW_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def smp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6388 LSP Hierarchy Supporting Shared Mesh Protection SHARE/PROTECT route.

    Provider ``smp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="smp",
        description=(
            "Drive a first-class RFC 6388 session: bind a loopback LSP Hierarchy "
            "Supporting Shared Mesh Protection origin, send a SHARE "
            "with a non-empty smpid, lockstep a PROTECT that carries the stored "
            "smpdigest, independently poll the stored smpdigest on a later "
            "client socket, and read the sealed smpdigest. SMPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "share": {"type": "boolean"},
                "protect": {"type": "boolean"},
                "smpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_smpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=SMP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def fmoam_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6427 MPLS Fault Management Operations, Administration, and Maintenance (OAM) FM/AIS route.

    Provider ``fmoam`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="fmoam",
        description=(
            "Drive a first-class RFC 6427 session: bind a loopback MPLS Fault "
            "Management Operations, Administration, and Maintenance origin, send a FM "
            "with a non-empty fmoamid, lockstep a AIS that carries the stored "
            "fmoamdigest, independently poll the stored fmoamdigest on a later "
            "client socket, and read the sealed fmoamdigest. FMOAMID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "fm": {"type": "boolean"},
                "ais": {"type": "boolean"},
                "fmoamdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_fmoamid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=FMOAM_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )



def pcv_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6428 Proactive Connectivity Verification, Continuity Check, and Remote Defect Indication for the MPLS Transport Profile CC/CV route.

    Provider ``pcv`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pcv",
        description=(
            "Drive a first-class RFC 6428 session: bind a loopback Proactive Connectivity "
            "Verification, Continuity Check, and Remote Defect Indication origin, send a CC "
            "with a non-empty pcvid, lockstep a CV that carries the stored "
            "pcvdigest, independently poll the stored pcvdigest on a later "
            "client socket, and read the sealed pcvdigest. PCVID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "cc": {"type": "boolean"},
                "cv": {"type": "boolean"},
                "pcvdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pcvid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PCV_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def lilb_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6435 A Protocol for Lock Instruct and Loopback of MPLS Transport Profile (MPLS-TP) OAM LI/LB route.

    Provider ``lilb`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="lilb",
        description=(
            "Drive a first-class RFC 6435 session: bind a loopback A Protocol for Lock Instruct "
            "and Loopback of MPLS Transport Profile origin, send a LI "
            "with a non-empty lilbid, lockstep a LB that carries the stored "
            "lilbdigest, independently poll the stored lilbdigest on a later "
            "client socket, and read the sealed lilbdigest. LILBID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "li": {"type": "boolean"},
                "lb": {"type": "boolean"},
                "lilbdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_lilbid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=LILB_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def pwst_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6478 Pseudowire Status for Static Pseudowires STATUS/ACK route.

    Provider ``pwst`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="pwst",
        description=(
            "Drive a first-class RFC 6478 session: bind a loopback Pseudowire Status "
            "for Static Pseudowires origin, send a STATUS "
            "with a non-empty pwstid, lockstep an ACK that carries the stored "
            "pwstdigest, independently poll the stored pwstdigest on a later "
            "client socket, and read the sealed pwstdigest. PWSTID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "status": {"type": "boolean"},
                "ack": {"type": "boolean"},
                "pwstdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_pwstid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=PWST_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def mldp_tool_descriptor(*, session_id: str | None = None) -> ToolDescriptor:
    """Descriptor for the first-party RFC 6512 Using Multipoint LDP When the Backbone Has No Route to the Root MLDP/ROOT route.

    Provider ``mldp`` is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing the tool never makes a
    live endpoint silently executable — a caller must opt the provider in.
    """

    return ToolDescriptor(
        name="mldp",
        description=(
            "Drive a first-class RFC 6512 session: bind a loopback Using Multipoint LDP "
            "When the Backbone Has No Route to the Root origin, send a MLDP "
            "with a non-empty mldpid, lockstep a ROOT that carries the stored "
            "mldpdigest, independently poll the stored mldpdigest on a later "
            "client socket, and read the sealed mldpdigest. MLDPID-gated exchanges "
            "stay sealed as digest-chained actuation traces."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["bind", "publish", "read", "close"],
                },
                "token": {"type": "string"},
                "mldp": {"type": "boolean"},
                "root": {"type": "boolean"},
                "mldpdigest": {"type": "boolean"},
                "replay": {"type": "boolean"},
                "use_mldpid": {"type": "boolean"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        provider=MLDP_TOOL_PROVIDER,
        session_id=session_id,
        tool_type="function",
    )


def load_single_file_agent_tool_descriptors(path: Path, *, session_id: str | None = None) -> list[ToolDescriptor]:
    """Load function tool descriptors from a compact single-file agent YAML config."""

    config = parse_single_file_agent_yaml(path.read_text(encoding="utf-8"))
    return tool_descriptors_from_agent_config(config, session_id=session_id)


def parse_single_file_agent_yaml(text: str) -> dict[str, Any]:
    """Parse a single-file agent YAML document without requiring PyYAML at runtime.

    If PyYAML is installed we use it. The fallback intentionally supports the compact
    single-file shape used by local fixtures: top-level mappings, one nested mapping
    level, and inline JSON values for schemas.
    """

    try:
        import yaml  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return _parse_simple_agent_yaml(text)

    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("single-file agent YAML must contain a mapping")
    return loaded


def tool_descriptors_from_agent_config(
    config: Mapping[str, Any], *, session_id: str | None = None
) -> list[ToolDescriptor]:
    """Return executable descriptors for function tools declared by an agent config."""

    tools = config.get("tools")
    if not isinstance(tools, Mapping):
        return []

    descriptors: list[ToolDescriptor] = []
    for name, raw_tool in tools.items():
        if not isinstance(name, str) or not isinstance(raw_tool, Mapping):
            continue
        tool_type = str(raw_tool.get("type") or "").strip()
        if tool_type != "function":
            continue
        callable_path = str(raw_tool.get("callable") or "").strip()
        if not callable_path:
            raise ValueError(f"function tool {name!r} is missing callable")
        parameters = raw_tool.get("parameters")
        if parameters is not None and not isinstance(parameters, Mapping):
            raise ValueError(f"function tool {name!r} parameters must be a mapping")
        descriptors.append(
            ToolDescriptor(
                name=name,
                description=str(raw_tool.get("description") or ""),
                parameters=parameters,
                provider="function",
                session_id=session_id,
                tool_type=tool_type,
                callable_path=callable_path,
            )
        )
    return descriptors


def executable_tool_registry(
    descriptors: Sequence[ToolDescriptor],
    *,
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> dict[str, dict[str, Any]]:
    """Build stable model-facing metadata for executable local tools."""

    return {
        descriptor.name: descriptor.to_call_metadata()
        for descriptor in descriptors
        if route_tool_descriptor(descriptor, tool_call_policy_evaluator=tool_call_policy_evaluator).executable
    }


MCP_TOOL_PROVIDER = "mcp"

# MCP tool annotations (Model Context Protocol spec) mapped onto local risk
# flags. Imported tools keep these flags so policy and review gates can see
# the remote server's own declarations.
MCP_ANNOTATION_RISK_FLAGS: tuple[tuple[str, str], ...] = (
    ("destructiveHint", "destructive"),
    ("openWorldHint", "open-world"),
)


def extract_mcp_tool_list(payload: Any) -> list[Mapping[str, Any]]:
    """Extract tool objects from an MCP ``tools/list`` payload.

    Accepts a JSON-RPC response envelope (``{"result": {"tools": [...]}}``), a
    bare result object (``{"tools": [...]}``), or a plain tool list. Entries
    without a non-empty string ``name`` are dropped deterministically.
    """

    tools: Any = []
    if isinstance(payload, list):
        tools = payload
    elif isinstance(payload, Mapping):
        inner: Any = payload.get("result") if isinstance(payload.get("result"), Mapping) else payload
        if isinstance(inner, Mapping) and isinstance(inner.get("tools"), list):
            tools = inner["tools"]
    return [tool for tool in tools if isinstance(tool, Mapping) and str(tool.get("name") or "").strip()]


def tool_descriptors_from_mcp_tools(
    payload: Any,
    *,
    server_name: str = "mcp",
    session_id: str | None = None,
) -> list[ToolDescriptor]:
    """Convert an MCP ``tools/list`` payload into routable local descriptors.

    Names are namespaced ``<server_name>:<tool>`` so tools from different MCP
    servers cannot collide with each other or with local tools. Descriptors
    carry provider ``"mcp"``, which is deliberately absent from
    ``DEFAULT_EXECUTABLE_TOOL_PROVIDERS``: importing an external tool never
    makes it silently executable — a caller must opt the provider in.
    """

    server = str(server_name or "").strip() or "mcp"
    descriptors: list[ToolDescriptor] = []
    for tool in extract_mcp_tool_list(payload):
        name = str(tool["name"]).strip()
        schema = tool.get("inputSchema")
        annotations = tool.get("annotations")
        annotations = annotations if isinstance(annotations, Mapping) else {}
        risk_flags = tuple(
            flag for hint, flag in MCP_ANNOTATION_RISK_FLAGS if annotations.get(hint) is True
        )
        descriptors.append(
            ToolDescriptor(
                name=f"{server}:{name}",
                description=str(tool.get("description") or ""),
                parameters=dict(schema) if isinstance(schema, Mapping) else None,
                provider=MCP_TOOL_PROVIDER,
                session_id=session_id,
                tool_type="function",
                risk_flags=risk_flags,
            )
        )
    return descriptors


def builtin_mcp_tool_import_proof() -> dict[str, Any]:
    """Registered proof for ``capability.mcp-tool-import``.

    Converts a representative MCP ``tools/list`` JSON-RPC response, checks the
    descriptor shape (namespacing, schema passthrough, annotation risk flags),
    and proves fail-closed routing: imported MCP tools are unsupported under
    default providers and executable only after explicit provider opt-in.
    """

    sample = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file from the workspace",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                    "annotations": {"readOnlyHint": True},
                },
                {
                    "name": "delete_file",
                    "description": "Delete a file from the workspace",
                    "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
                    "annotations": {"destructiveHint": True, "openWorldHint": False},
                },
                {"name": ""},
                "not-a-tool",
            ]
        },
    }
    descriptors = tool_descriptors_from_mcp_tools(sample, server_name="fs")
    shape_ok = (
        len(descriptors) == 2
        and descriptors[0].name == "fs:read_file"
        and descriptors[0].provider == MCP_TOOL_PROVIDER
        and descriptors[0].parameters
        == {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        and descriptors[1].risk_flags == ("destructive",)
    )
    default_decisions = route_tool_descriptors(descriptors)
    fail_closed = all(decision.route == UNSUPPORTED_TOOL_ROUTE for decision in default_decisions)
    opt_in_decisions = [
        route_tool_descriptor(
            descriptor,
            executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MCP_TOOL_PROVIDER),
        )
        for descriptor in descriptors
    ]
    opt_in_ok = all(decision.executable for decision in opt_in_decisions)
    return {
        "ok": bool(shape_ok and fail_closed and opt_in_ok),
        "imported_count": len(descriptors),
        "fail_closed_by_default": fail_closed,
        "executable_after_opt_in": opt_in_ok,
        "names": [descriptor.name for descriptor in descriptors],
    }


def builtin_multi_kernel_harness_proof() -> dict[str, Any]:
    """Registered proof for ``capability.multi-kernel-harness-routing``.

    Grounded in the live-trend signal "runs anywhere, uses anything"
    (multi-provider agent CLIs). Proves that the built-in provider harness
    catalog covers every first-class local CLI kernel this repository runs
    (Codex, Grok, Kimi), that discovery routes deterministically to whichever
    kernel is installed, that first-class kernels outrank third-party SDK
    shims, and that a machine with none of them still falls through to the
    dependency-free function agent. Hermetic: command availability is
    injected, never probed from the host.
    """

    catalog = default_provider_harnesses()
    by_name = {harness.name: harness for harness in catalog}
    first_class = {"codex-cli": "codex", "grok-cli": "grok", "kimi-cli": "kimi"}
    catalog_covers_kernels = all(
        name in by_name and by_name[name].required_commands == (command,) and by_name[name].provider == command
        for name, command in first_class.items()
    )

    def selected_with(commands: set[str]) -> str | None:
        selection = select_provider_harness(
            catalog,
            installed_modules=set(),
            available_commands=commands,
            environ={},
            platform="linux",
        )
        return selection.selected.name if selection.selected else None

    routes = {
        "kimi_only": selected_with({"kimi"}),
        "grok_only": selected_with({"grok"}),
        "all_kernels": selected_with({"codex", "grok", "kimi"}),
        "grok_and_kimi": selected_with({"grok", "kimi"}),
        "none": selected_with(set()),
    }
    routing_ok = routes == {
        "kimi_only": "kimi-cli",
        "grok_only": "grok-cli",
        "all_kernels": "codex-cli",
        "grok_and_kimi": "grok-cli",
        "none": "single-file-function-agent",
    }

    statuses = discover_provider_harnesses(
        catalog,
        installed_modules=set(),
        available_commands={"kimi"},
        environ={},
        platform="linux",
    )
    skip_map = {status.harness.name: status.skip_reasons for status in statuses}
    deterministic_skips = (
        skip_map.get("codex-cli") == ("missing_dependency:codex",)
        and skip_map.get("grok-cli") == ("missing_dependency:grok",)
        and skip_map.get("kimi-cli") == ()
    )

    return {
        "ok": bool(catalog_covers_kernels and routing_ok and deterministic_skips),
        "catalog_covers_first_class_kernels": catalog_covers_kernels,
        "routes": routes,
        "routing_ok": routing_ok,
        "deterministic_skip_reasons": deterministic_skips,
        "harness_count": len(catalog),
    }


def build_headless_function_call_dispatch_report(
    events: Sequence[Mapping[str, Any]],
    descriptors: Sequence[ToolDescriptor],
    *,
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> dict[str, Any]:
    """Normalize headless function_call events and prove they reach tool routing.

    This is a dry-run dispatch report: it checks whether each model-emitted event
    has an executable local descriptor after policy routing, but never invokes the
    descriptor callable or exports raw arguments.
    """

    decisions = {
        decision.descriptor.name: decision
        for decision in route_tool_descriptors(
            descriptors,
            tool_call_policy_evaluator=tool_call_policy_evaluator,
        )
    }
    normalized_events = [
        normalize_headless_function_call_event(event) for event in events if is_headless_function_call_event(event)
    ]
    dispatches: list[dict[str, Any]] = []
    for index, event in enumerate(normalized_events):
        name = str(event["name"])
        decision = decisions.get(name)
        if decision is None:
            route = "missing_handler"
            reasons = ["missing_executable_handler"]
        elif decision.executable:
            route = "dispatched"
            reasons = []
        else:
            route = decision.route
            reasons = list(decision.reasons)
        dispatches.append(
            {
                "event_index": index,
                "event_id": event["event_id"],
                "name": name,
                "route": route,
                "reasons": reasons,
                "arguments_hash": event["arguments_hash"],
                "arguments_exported": False,
            }
        )

    dispatched_count = sum(1 for dispatch in dispatches if dispatch["route"] == "dispatched")
    missing_handler_count = sum(1 for dispatch in dispatches if dispatch["route"] == "missing_handler")
    blocked_count = sum(1 for dispatch in dispatches if dispatch["route"] not in {"dispatched", "missing_handler"})
    dropped_count = len(events) - len(normalized_events)
    route_counts: dict[str, int] = {}
    for dispatch in dispatches:
        route = str(dispatch["route"])
        route_counts[route] = route_counts.get(route, 0) + 1
    all_function_calls_dispatched = bool(normalized_events) and dispatched_count == len(normalized_events)
    return {
        "schema_version": 1,
        "event_count": len(events),
        "function_call_event_count": len(normalized_events),
        "dispatch_attempt_count": len(dispatches),
        "dispatched_count": dispatched_count,
        "blocked_count": blocked_count,
        "missing_handler_count": missing_handler_count,
        "dropped_event_count": dropped_count,
        "route_counts": route_counts,
        "all_function_calls_dispatched": all_function_calls_dispatched,
        "dispatches": dispatches,
        "raw_arguments_exported": False,
        "tools_executed": False,
    }


def is_headless_function_call_event(event: Mapping[str, Any]) -> bool:
    event_type = str(event.get("type") or event.get("event") or "").strip()
    return event_type in HEADLESS_FUNCTION_CALL_EVENT_TYPES


def normalize_headless_function_call_event(event: Mapping[str, Any]) -> dict[str, Any]:
    function = event.get("function") if isinstance(event.get("function"), Mapping) else {}
    name = str(event.get("name") or function.get("name") or "").strip()
    arguments = event.get("arguments") if "arguments" in event else function.get("arguments")
    event_id = str(event.get("id") or event.get("call_id") or name or "headless-function-call")
    return {
        "event_id": event_id,
        "name": name,
        "arguments_hash": _stable_tool_json_hash(arguments) if arguments is not None else None,
    }


def _stable_tool_json_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _parse_simple_agent_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_key: str | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            pending_key = key
            continue

        parent[key] = _parse_simple_yaml_scalar(value)
        pending_key = None

    if pending_key is not None and root.get(pending_key) == {}:
        raise ValueError(f"empty mapping for {pending_key!r}")
    return root


def _parse_simple_yaml_scalar(value: str) -> Any:
    if value.startswith(("{", "[")):
        return json.loads(value)
    if value in {"true", "false"}:
        return value == "true"
    if value == "null":
        return None
    return value.strip("\"'")
