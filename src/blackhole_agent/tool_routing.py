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
