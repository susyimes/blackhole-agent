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
