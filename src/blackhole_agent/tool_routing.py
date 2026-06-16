"""Tool descriptor metadata helpers for local agent routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


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
