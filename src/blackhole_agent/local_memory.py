"""Local first-party memory tool with privacy guards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

MemoryAction = Literal["write", "read", "list", "delete"]

KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    ("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assignment_secret", re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*\S+")),
    ("email_address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
)


class MemoryPrivacyError(ValueError):
    """Raised when a memory write attempts to store secret or private data."""


class MemoryIsolationError(ValueError):
    """Raised when a memory path would escape its configured root."""


@dataclass(frozen=True)
class MemoryEntry:
    """A single non-secret memory item."""

    key: str
    value: str
    tags: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: utc_now_iso())
    updated_at: str = field(default_factory=lambda: utc_now_iso())

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "key": self.key,
            "tags": list(self.tags),
            "updated_at": self.updated_at,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryEntry":
        return cls(
            key=str(payload.get("key") or ""),
            value=str(payload.get("value") or ""),
            tags=tuple(str(tag) for tag in payload.get("tags", []) if str(tag).strip()),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
        )


class LocalMemoryStore:
    """JSON-backed local memory scoped to a single namespace under a root directory."""

    def __init__(self, root: Path, *, namespace: str = "agent") -> None:
        self.root = root
        self.namespace = validate_namespace(namespace)
        self.path = isolated_memory_path(root, self.namespace)

    def write(self, key: str, value: str, *, tags: list[str] | tuple[str, ...] = ()) -> MemoryEntry:
        key = validate_key(key)
        normalized_tags = tuple(validate_key(str(tag)) for tag in tags if str(tag).strip())
        assert_public_memory_payload(key=key, value=value, tags=normalized_tags)
        payload = self._load()
        existing = payload["entries"].get(key, {})
        now = utc_now_iso()
        entry = MemoryEntry(
            key=key,
            value=value,
            tags=normalized_tags,
            created_at=str(existing.get("created_at") or now),
            updated_at=now,
        )
        payload["entries"][key] = entry.to_dict()
        self._save(payload)
        return entry

    def read(self, key: str) -> MemoryEntry | None:
        key = validate_key(key)
        payload = self._load()
        entry = payload["entries"].get(key)
        if not isinstance(entry, dict):
            return None
        return MemoryEntry.from_dict(entry)

    def list(self, *, tag: str | None = None) -> list[MemoryEntry]:
        tag_filter = validate_key(tag) if tag else None
        payload = self._load()
        entries = [
            MemoryEntry.from_dict(entry)
            for entry in payload["entries"].values()
            if isinstance(entry, dict)
        ]
        if tag_filter is not None:
            entries = [entry for entry in entries if tag_filter in entry.tags]
        return sorted(entries, key=lambda entry: entry.key)

    def delete(self, key: str) -> bool:
        key = validate_key(key)
        payload = self._load()
        existed = key in payload["entries"]
        payload["entries"].pop(key, None)
        self._save(payload)
        return existed

    def execute(
        self,
        action: MemoryAction,
        *,
        key: str | None = None,
        value: str | None = None,
        tags: list[str] | tuple[str, ...] = (),
        tag: str | None = None,
    ) -> dict[str, Any]:
        """Execute the local-memory tool action and return JSON-serializable data."""

        if action == "write":
            if key is None or value is None:
                raise ValueError("write requires key and value")
            return {"entry": self.write(key, value, tags=tags).to_dict(), "status": "written"}
        if action == "read":
            if key is None:
                raise ValueError("read requires key")
            entry = self.read(key)
            return {"entry": entry.to_dict() if entry else None, "status": "found" if entry else "missing"}
        if action == "list":
            return {"entries": [entry.to_dict() for entry in self.list(tag=tag)], "status": "listed"}
        if action == "delete":
            if key is None:
                raise ValueError("delete requires key")
            return {"deleted": self.delete(key), "status": "deleted"}
        raise ValueError(f"unsupported memory action: {action}")

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"entries": {}, "namespace": self.namespace, "schema_version": 1}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{self.path} must contain a JSON object")
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            payload["entries"] = {}
        payload["namespace"] = self.namespace
        payload["schema_version"] = 1
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def isolated_memory_path(root: Path, namespace: str) -> Path:
    root = root.resolve()
    path = (root / f"{validate_namespace(namespace)}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise MemoryIsolationError(f"memory path escapes configured root: {path}") from error
    return path


def validate_namespace(value: str) -> str:
    namespace = str(value or "").strip()
    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise ValueError("memory namespace must be 1-64 chars of letters, digits, dot, colon, underscore, or hyphen")
    return namespace


def validate_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("memory keys and tags must be 1-128 chars of letters, digits, dot, colon, underscore, or hyphen")
    return key


def assert_public_memory_payload(*, key: str, value: str, tags: tuple[str, ...]) -> None:
    checked = {"key": key, "tags": " ".join(tags), "value": value}
    findings = sorted({label for text in checked.values() for label, pattern in SECRET_PATTERNS if pattern.search(text)})
    if findings:
        raise MemoryPrivacyError(f"memory write rejected by privacy guard: {', '.join(findings)}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
