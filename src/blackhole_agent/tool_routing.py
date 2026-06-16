"""Tool descriptor metadata helpers for local agent routing."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Mapping, Sequence


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

    def compatibility_key(self) -> str:
        """Key cache entries by every field that changes call compatibility."""

        payload = {
            "callable_path": self.callable_path,
            "description": self.description,
            "name": self.name,
            "parameters": self.parameters,
            "provider": self.provider,
            "session_id": self.session_id,
            "tool_type": self.tool_type,
        }
        return canonical_tool_schema(payload)

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
        if self.parameters is not None:
            metadata["parameters"] = dict(self.parameters)
        return metadata


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


def executable_tool_registry(descriptors: list[ToolDescriptor]) -> dict[str, dict[str, Any]]:
    """Build stable model-facing metadata for executable local tools."""

    return {descriptor.name: descriptor.to_call_metadata() for descriptor in descriptors}


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
