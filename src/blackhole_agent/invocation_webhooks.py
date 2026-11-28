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
- a retry to the same hook returns HTTP 409 ``webhook_replayed`` with the
  original run id, even through another server sharing the root. GET shows
  the saved result or ``interrupted`` if its worker exited before saving it.
  Older fingerprints still receive HTTP 409 without a run id.
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
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.file_guard import atomic_write_json, file_guard, try_file_guard
from blackhole_agent.session_notify import (
    SIGNATURE_HEADER,
    sign_notify_body,
    verify_notify_signature,
)

SCHEMA_VERSION = 1
RUN_SCHEMA_VERSION = 2
ACTIVE_STATUSES = frozenset({"accepted", "running"})
INTERRUPTED_DETAIL = "Worker exited before saving its result. Check tool effects."
RECEIPT_FIELDS = ("run_id", "hook", "capability_id", "created_at")
WEBHOOK_SECRET_ENV = "BLACKHOLE_WEBHOOK_SECRET"
WEBHOOK_HOOK_ENV = "BLACKHOLE_WEBHOOK_HOOK"
HOOKS_PATH_PREFIX = "/hooks/"
RUNS_RELATIVE = Path(".blackhole-agent") / "webhook-runs"
DELIVERIES_RELATIVE = Path(".blackhole-agent") / "webhook-deliveries.json"
MAX_DELIVERIES = 4096
MIN_SECRET_CHARS = 8
MAX_SECRET_CHARS = 128
MAX_HOOKS = 64
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
        self._delivery_limit = MAX_DELIVERIES if delivery_limit is None else int(delivery_limit)
        if self._delivery_limit < 1:
            raise ValueError("delivery_limit must be at least 1")

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
        path = self.root / RUNS_RELATIVE / f"{ident}.json"
        record = self._read_run(path)
        if record.get("schema_version") != RUN_SCHEMA_VERSION or record.get("status") not in ACTIVE_STATUSES:
            return public_run_record(record)
        try:
            lease = try_file_guard(path)
            if lease is not None:
                with lease:
                    # The worker could have finished between our first read and the lock.
                    record = self._read_run(path)
                    if record["status"] in ACTIVE_STATUSES:
                        record.update(status="interrupted", error=INTERRUPTED_DETAIL)
                        atomic_write_json(path, record)
        except OSError as exc:
            raise WebhookError(500, "webhook_run_unavailable") from exc
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
        run_id = uuid.uuid4().hex
        record = {
            "schema_version": RUN_SCHEMA_VERSION,
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
        path = self.root / RUNS_RELATIVE / f"{run_id}.json"
        lease = ExitStack()
        try:
            self._reserve(raw_body, record, path, lease)
            worker = threading.Thread(
                target=self._run_tool, args=(path, dict(record), provided_input, self._invoke, lease),
                name=f"webhook-run-{run_id[:8]}", daemon=True,
            )
            try:
                worker.start()
            except (RuntimeError, OSError) as exc:
                raise WebhookError(503, "webhook_worker_unavailable", {"run_id": run_id}) from exc
        except BaseException:
            lease.close()
            raise
        return public_run_record(record)

    def _run_tool(
        self, path: Path, record: dict[str, Any], inputs: dict[str, Any], invoke: InvokeFn, lease: ExitStack,
    ) -> None:
        with lease:
            record["status"] = "running"
            atomic_write_json(path, record)
            try:
                result = invoke(self.root, record["capability_id"], inputs, cancel_event=None)
                result = result if isinstance(result, Mapping) else {}
                output = result.get("output")
                record.update(
                    status="completed", output=dict(output) if isinstance(output, Mapping) else output,
                    artifacts=list(result.get("artifacts") or []), invocation_id=result.get("invocation_id"),
                )
            except Exception as exc:
                error = str(getattr(exc, "error", None) or f"{type(exc).__name__}: {exc}")
                record.update(status="failed", error=error[:400])
            atomic_write_json(path, record, ensure_ascii=True)

    @staticmethod
    def _delivery_index(path: Path) -> dict[str, dict[str, str] | None]:
        """Preserve FIFO order and legacy reservations that never recorded a run id."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        fingerprints = payload["fingerprints"]
        receipts = payload.get("receipts", {})
        if not isinstance(fingerprints, list) or not isinstance(receipts, dict):
            raise ValueError("invalid webhook delivery index")
        if not all(isinstance(key, str) for key in fingerprints):
            raise ValueError("invalid webhook fingerprint")
        for receipt in receipts.values():
            if not isinstance(receipt, dict) or not all(isinstance(receipt.get(k), str) for k in RECEIPT_FIELDS):
                raise ValueError("invalid webhook receipt")
            if not re.fullmatch(r"[a-f0-9]{32}", receipt["run_id"]):
                raise ValueError("invalid webhook run id")
        return {key: receipts.get(key) for key in fingerprints}

    def _retry_details(self, original: dict[str, str] | None, attempt: dict[str, Any]) -> dict[str, str]:
        if original is None or any(original[key] != attempt[key] for key in ("hook", "capability_id")):
            return {}
        run_id = original["run_id"]
        path = self.root / RUNS_RELATIVE / f"{run_id}.json"
        try:
            path.stat()
        except FileNotFoundError:
            # The index guard excludes a live admission. A crash in the
            # interval between its two writes cannot have dispatched a worker.
            recovered = dict(attempt, run_id=run_id, created_at=original["created_at"],
                             status="interrupted", error=INTERRUPTED_DETAIL)
            atomic_write_json(path, recovered)
        return {"run_id": run_id}

    def _reserve(self, raw: bytes, record: dict[str, Any], run_path: Path, lease: ExitStack) -> None:
        index_path = self.root / DELIVERIES_RELATIVE
        fingerprint = hashlib.sha256(raw).hexdigest()
        try:
            run_path.parent.mkdir(parents=True, exist_ok=True)
            with file_guard(index_path):
                deliveries = self._delivery_index(index_path)
                if fingerprint in deliveries:
                    raise WebhookError(409, "webhook_replayed", self._retry_details(deliveries[fingerprint], record))
                # One replacement binds the fingerprint, destination and run id.
                # No acknowledgment or worker can precede that commit.
                deliveries[fingerprint] = {key: record[key] for key in RECEIPT_FIELDS}
                retained = list(deliveries)[-self._delivery_limit:]
                atomic_write_json(index_path, {
                    "schema_version": SCHEMA_VERSION, "fingerprints": retained,
                    "receipts": {key: deliveries[key] for key in retained if deliveries[key]},
                })
                lease.enter_context(file_guard(run_path))
                atomic_write_json(run_path, record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WebhookError(500, "webhook_replay_store_unreadable") from exc

    @staticmethod
    def _read_run(path: Path) -> dict[str, Any]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("invalid webhook run")
            return record
        except FileNotFoundError as exc:
            raise WebhookError(404, "webhook_run_unknown") from exc
        except (OSError, ValueError) as exc:
            raise WebhookError(500, "webhook_run_unreadable") from exc


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
