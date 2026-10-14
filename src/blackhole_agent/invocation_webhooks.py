"""HMAC-signed inbound webhooks that start a governed live-plane invoke.

``POST /invoke`` needs a connected HTTP client for the whole tool runtime, so
CI that can only deliver a signed callback cannot start a governed tool.
This module is the opt-in inbound route:

- ``--webhook-secret`` plus ``--webhook-hook NAME=id`` (or the matching env)
  maps a URL name to one invocable tool id
- ``POST /hooks/{name}`` with a valid ``X-Hub-Signature-256`` over the raw
  body returns HTTP 202 with a run id and continues after the client hangs up
- ``GET /hooks/{run_id}`` returns accepted/running/completed/failed plus the
  tool output
- missing or wrong signatures are HTTP 401 and never spawn, and they are
  not recorded, so a later correct signature of that body can still run
- an unknown hook name after a valid signature is HTTP 404 and is not recorded
- an identical raw body that already passed the signature check is a replay:
  its SHA-256 is persisted under the service root and a second POST is HTTP
  409 ``webhook_replayed`` without spawning, including after a process
  restart that reuses that root. A different signed body is a new delivery
- a plane without the secret stays fail-closed: ``GET /health`` reports
  ``webhook_hooks`` false and ``webhook_replay_guard`` false, and
  ``POST /hooks`` is HTTP 404

Honesty boundary: HMAC over the raw body is still the authenticator. The
replay store keeps a bounded number of fingerprints and drops the oldest,
so a body evicted from that store can be accepted again. Hook names are an
allowlist, not a bearer. Runs persist under the service root; operators
delete the workspace to drop them, matching receipts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.session_notify import (
    SIGNATURE_HEADER,
    sign_notify_body,
    verify_notify_signature,
)

SCHEMA_VERSION = 1
WEBHOOK_SECRET_ENV = "BLACKHOLE_WEBHOOK_SECRET"
WEBHOOK_HOOK_ENV = "BLACKHOLE_WEBHOOK_HOOK"
HOOKS_PATH_PREFIX = "/hooks/"
RUNS_RELATIVE = Path(".blackhole-agent") / "webhook-runs"
DELIVERIES_RELATIVE = Path(".blackhole-agent") / "webhook-deliveries.json"
MAX_DELIVERIES = 4096
MIN_SECRET_CHARS = 8
MAX_SECRET_CHARS = 128
MAX_HOOKS = 64
MAX_RUNS = 256
HOOK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

InvokeFn = Callable[..., dict[str, Any]]


class WebhookConfigError(ValueError):
    """Fail-closed refusal of a malformed webhook configuration."""

    def __init__(self, detail: str) -> None:
        self.payload = {
            "ok": False,
            "error": "webhook_config_invalid",
            "detail": str(detail),
        }
        super().__init__(detail)


class WebhookError(Exception):
    """Fail-closed webhook refusal with an HTTP status."""

    def __init__(self, status: int, error: str, extra: Mapping[str, Any] | None = None) -> None:
        super().__init__(error)
        self.status = int(status)
        self.error = str(error)
        self.extra = dict(extra or {})
        self.payload = {"ok": False, "error": self.error, **self.extra}


@dataclass(frozen=True)
class WebhookConfig:
    """Parsed inbound-hook allowlist. ``enabled`` is true when a secret and hooks exist."""

    secret: str = ""
    hooks: tuple[tuple[str, str], ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.secret) and bool(self.hooks)

    def capability_id(self, name: str) -> str | None:
        wanted = str(name or "")
        for hook, capability_id in self.hooks:
            if hook == wanted:
                return capability_id
        return None

    def health(self) -> dict[str, Any]:
        return {
            "webhook_hooks": self.enabled,
            "webhook_hook_count": len(self.hooks),
        }


DISABLED_WEBHOOKS = WebhookConfig()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_webhook_secret(secret: Any) -> str:
    if not isinstance(secret, str):
        raise WebhookConfigError("webhook secret must be a string")
    if len(secret) < MIN_SECRET_CHARS or len(secret) > MAX_SECRET_CHARS:
        raise WebhookConfigError(
            f"webhook secret must be {MIN_SECRET_CHARS}–{MAX_SECRET_CHARS} characters"
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in secret):
        raise WebhookConfigError("webhook secret must not contain control characters")
    return secret


def parse_webhook_hook_clause(raw: str) -> tuple[str, str]:
    """Parse one ``NAME=capability_id`` clause."""

    text = str(raw or "").strip()
    if not text:
        raise WebhookConfigError("webhook-hook clause is empty")
    if "=" not in text:
        raise WebhookConfigError("webhook-hook clause must be NAME=capability_id")
    name, _, rest = text.partition("=")
    name = name.strip()
    capability_id = rest.strip()
    if not HOOK_NAME_RE.fullmatch(name):
        raise WebhookConfigError("webhook-hook name must be 1-64 letters, digits, or ._-")
    if not CAPABILITY_ID_RE.fullmatch(capability_id):
        raise WebhookConfigError(f"webhook-hook tool id is invalid: {capability_id!r}")
    return name, capability_id


def _hooks_from_env_text(text: str) -> list[tuple[str, str]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise WebhookConfigError(f"{WEBHOOK_HOOK_ENV} is not JSON: {exc}") from exc
        if isinstance(payload, dict):
            parsed: list[tuple[str, str]] = []
            for name, value in payload.items():
                parsed.append(parse_webhook_hook_clause(f"{name}={value}"))
            return parsed
        if isinstance(payload, list):
            return [parse_webhook_hook_clause(str(item)) for item in payload]
        raise WebhookConfigError(f"{WEBHOOK_HOOK_ENV} JSON must be an object or array")
    parts = [part.strip() for part in re.split(r"[\n;]+", stripped) if part.strip()]
    return [parse_webhook_hook_clause(part) for part in parts]


def resolve_webhook_config(
    secret: str | None = None,
    hooks: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> WebhookConfig:
    """Return the inbound-hook config from CLI flags or environment."""

    source = env if env is not None else os.environ
    secret_text = str(secret if secret is not None else source.get(WEBHOOK_SECRET_ENV) or "").strip()
    clauses = [str(item).strip() for item in (hooks or ()) if str(item).strip()]
    if not clauses:
        env_text = str(source.get(WEBHOOK_HOOK_ENV) or "").strip()
        if env_text.startswith("{") or env_text.startswith("["):
            clauses = [f"{name}={capability_id}" for name, capability_id in _hooks_from_env_text(env_text)]
        else:
            clauses = [part.strip() for part in re.split(r"[\n;]+", env_text) if part.strip()]
    secret_set = bool(secret_text)
    hook_set = bool(clauses)
    if not secret_set and not hook_set:
        return DISABLED_WEBHOOKS
    if secret_set != hook_set:
        raise WebhookConfigError("webhook secret and at least one hook must be supplied together")
    parsed_secret = validate_webhook_secret(secret_text)
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for clause in clauses:
        name, capability_id = parse_webhook_hook_clause(clause)
        if name in seen:
            raise WebhookConfigError(f"webhook-hook name is duplicated: {name}")
        seen.add(name)
        parsed.append((name, capability_id))
        if len(parsed) > MAX_HOOKS:
            raise WebhookConfigError(f"at most {MAX_HOOKS} webhook hooks are allowed")
    return WebhookConfig(secret=parsed_secret, hooks=tuple(parsed))


def parse_hooks_path(path: str) -> str | None:
    """Return the single ``/hooks/{segment}`` name, or None when the path is not a hook route."""

    raw = str(path or "").split("?", 1)[0]
    if raw in {"/hooks", "/hooks/"}:
        return ""
    if not raw.startswith(HOOKS_PATH_PREFIX):
        return None
    rest = raw[len(HOOKS_PATH_PREFIX) :]
    if not rest or "/" in rest:
        return None
    return rest


def public_run_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """HTTP copy of a run: no secret, stable keys."""

    return {
        "ok": True,
        "artifacts": list(record.get("artifacts") or []),
        "capability_id": record.get("capability_id"),
        "error": record.get("error"),
        "hook": record.get("hook"),
        "invocation_id": record.get("invocation_id"),
        "output": record.get("output"),
        "run_id": record.get("run_id"),
        "status": record.get("status"),
    }


def _runs_root(root: Path) -> Path:
    return Path(root).resolve() / RUNS_RELATIVE


class WebhookPlane:
    """Accept signed POSTs, run the mapped tool in the background, and serve run status."""

    def __init__(
        self,
        root: Path,
        config: WebhookConfig,
        *,
        invoke: InvokeFn | None = None,
        delivery_limit: int | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.config = config
        self._invoke = invoke
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._delivery_limit = MAX_DELIVERIES if delivery_limit is None else int(delivery_limit)
        if self._delivery_limit < 1:
            raise ValueError("delivery_limit must be at least 1")
        self._deliveries: list[str] | None = None

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def health(self) -> dict[str, Any]:
        report = dict(self.config.health())
        report["webhook_replay_guard"] = bool(self.enabled)
        return report

    def get_run(self, run_id: str) -> dict[str, Any]:
        if not self.enabled:
            raise WebhookError(404, "webhook_disabled")
        ident = str(run_id or "")
        if RUN_ID_RE.fullmatch(ident) is None:
            raise WebhookError(400, "run_id must be 1-128 ASCII letters, digits, ._:-")
        record = self._load(ident)
        if record is None:
            raise WebhookError(404, "webhook_run_unknown")
        return public_run_record(record)

    def accept_post(self, name: str, raw_body: bytes, signature_header: str | None) -> dict[str, Any]:
        if not self.enabled:
            raise WebhookError(404, "webhook_disabled")
        hook = str(name or "")
        if not HOOK_NAME_RE.fullmatch(hook):
            raise WebhookError(404, "hook_unknown")
        if not raw_body:
            raise WebhookError(400, "missing or oversized body")
        header = str(signature_header or "")
        if not header.strip():
            raise WebhookError(401, "webhook_signature_required")
        if not verify_notify_signature(self.config.secret, raw_body, header):
            raise WebhookError(401, "webhook_signature_invalid")
        capability_id = self.config.capability_id(hook)
        if capability_id is None:
            raise WebhookError(404, "hook_unknown")
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebhookError(400, f"body is not valid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise WebhookError(400, "body must be a JSON object")
        provided_input = body.get("input") if "input" in body else body
        if not isinstance(provided_input, dict):
            raise WebhookError(422, "input must be a JSON object")
        if self._invoke is None:
            raise WebhookError(500, "webhook_invoke_unbound")
        if not self._claim_delivery(raw_body):
            raise WebhookError(409, "webhook_replayed")
        run_id = uuid.uuid4().hex
        record = {
            "schema_version": SCHEMA_VERSION,
            "artifacts": [],
            "capability_id": capability_id,
            "created_at": _utc_now_iso(),
            "error": None,
            "hook": hook,
            "invocation_id": None,
            "output": None,
            "run_id": run_id,
            "status": "accepted",
        }
        self._persist(record)
        worker = threading.Thread(
            target=self._run_tool,
            args=(run_id, capability_id, dict(provided_input)),
            name=f"webhook-run-{run_id[:8]}",
            daemon=True,
        )
        worker.start()
        return public_run_record(record)

    def _run_tool(self, run_id: str, capability_id: str, provided_input: dict[str, Any]) -> None:
        self._merge(run_id, {"status": "running"})
        invoke = self._invoke
        if invoke is None:
            self._merge(run_id, {"status": "failed", "error": "webhook_invoke_unbound"})
            return
        try:
            result = invoke(self.root, capability_id, provided_input, cancel_event=None)
        except Exception as exc:
            error = str(getattr(exc, "error", None) or f"{type(exc).__name__}: {exc}")
            self._merge(run_id, {"status": "failed", "error": error[:400]})
            return
        output = result.get("output") if isinstance(result, Mapping) else None
        artifacts = result.get("artifacts") if isinstance(result, Mapping) else None
        invocation_id = result.get("invocation_id") if isinstance(result, Mapping) else None
        self._merge(
            run_id,
            {
                "status": "completed",
                "output": dict(output) if isinstance(output, Mapping) else output,
                "artifacts": list(artifacts or []),
                "invocation_id": invocation_id,
                "error": None,
            },
        )

    def _deliveries_path(self) -> Path:
        return self.root / DELIVERIES_RELATIVE

    def _claim_delivery(self, raw_body: bytes) -> bool:
        """Record ``raw_body`` once. False means this exact body already ran."""

        fingerprint = hashlib.sha256(raw_body).hexdigest()
        with self._lock:
            seen = list(self._read_deliveries())
            if fingerprint in seen:
                return False
            seen.append(fingerprint)
            if len(seen) > self._delivery_limit:
                del seen[: len(seen) - self._delivery_limit]
            try:
                self._write_deliveries(seen)
            except OSError as exc:
                raise WebhookError(500, "webhook_replay_store_unreadable") from exc
            self._deliveries = seen
            return True

    def _read_deliveries(self) -> list[str]:
        if self._deliveries is not None:
            return self._deliveries
        path = self._deliveries_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._deliveries = []
            return self._deliveries
        except (OSError, json.JSONDecodeError) as exc:
            raise WebhookError(500, "webhook_replay_store_unreadable") from exc
        fingerprints = payload.get("fingerprints") if isinstance(payload, dict) else None
        if not isinstance(fingerprints, list) or not all(isinstance(item, str) for item in fingerprints):
            raise WebhookError(500, "webhook_replay_store_unreadable")
        self._deliveries = list(fingerprints)
        return self._deliveries

    def _write_deliveries(self, fingerprints: list[str]) -> None:
        path = self._deliveries_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            {"fingerprints": list(fingerprints), "schema_version": SCHEMA_VERSION},
            indent=2,
            sort_keys=True,
        )
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(path)

    def _path(self, run_id: str) -> Path:
        return _runs_root(self.root) / f"{run_id}.json"

    def _load(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            cached = self._runs.get(run_id)
            if cached is not None:
                return dict(cached)
        path = self._path(run_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        with self._lock:
            self._runs[run_id] = payload
        return dict(payload)

    def _persist(self, record: Mapping[str, Any]) -> None:
        run_id = str(record.get("run_id") or "")
        path = self._path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        encoded = json.dumps(payload, indent=2, sort_keys=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(encoded, encoding="utf-8")
        tmp.replace(path)
        with self._lock:
            self._runs[run_id] = payload
            if len(self._runs) > MAX_RUNS:
                extra = list(self._runs)[:-MAX_RUNS]
                for ident in extra:
                    self._runs.pop(ident, None)

    def _merge(self, run_id: str, updates: Mapping[str, Any]) -> None:
        record = self._load(run_id)
        if record is None:
            return
        record.update(dict(updates))
        self._persist(record)


def sign_webhook_body(secret: str, body: bytes) -> str:
    """Return the GitHub-style ``sha256=`` header for ``body``."""

    return sign_notify_body(secret, body)


__all__ = [
    "DISABLED_WEBHOOKS",
    "SIGNATURE_HEADER",
    "WEBHOOK_HOOK_ENV",
    "WEBHOOK_SECRET_ENV",
    "WebhookConfig",
    "WebhookConfigError",
    "WebhookError",
    "WebhookPlane",
    "parse_hooks_path",
    "parse_webhook_hook_clause",
    "public_run_record",
    "resolve_webhook_config",
    "sign_webhook_body",
    "validate_webhook_secret",
]
