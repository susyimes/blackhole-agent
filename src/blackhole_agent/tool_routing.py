"""Tool descriptor metadata helpers for local agent routing."""

from __future__ import annotations

import json
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
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> tuple[ToolRouteDecision, ...]:
    """Return inspectable routing decisions for a batch of descriptors."""

    return tuple(
        route_tool_descriptor(descriptor, tool_call_policy_evaluator=tool_call_policy_evaluator)
        for descriptor in descriptors
    )


def build_tool_routing_preflight(
    descriptors: Sequence[ToolDescriptor],
    *,
    required_tool_names: Sequence[str] = (),
    tool_call_policy_evaluator: ToolCallPolicyEvaluator | None = None,
) -> dict[str, Any]:
    """Return startup-safe diagnostics for local tool routing capabilities."""

    decisions = route_tool_descriptors(descriptors, tool_call_policy_evaluator=tool_call_policy_evaluator)
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
    """Return the built-in fallback order for locally supported agent providers."""

    return (
        ProviderHarness(
            name="codex-cli",
            provider="codex",
            priority=10,
            required_commands=("codex",),
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
