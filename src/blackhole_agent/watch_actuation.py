"""Drive a first-class path-watch tool through filesystem mutation observe.

Tool routing already fails missions that require ``watch``: hosted mutation
plugins stay on the unsupported MCP provider, and no first-party filesystem
observer is executable. Unbound therefore cannot subscribe to local path
mutations, consume CREATE/MODIFY events, or seal a change digest an
independent reader can re-open.

This module closes that hole:

- advertise a ``watch`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real on-disk watch root
- keep a missing-token and missing-root client so the hole stays falsifiable
- refuse CREATE/MODIFY/CONSUME until WATCH (subscribe) succeeds
- CREATE then MODIFY a beacon, CONSUME observer events, then independently
  re-hash the beacon from a fresh file open so skip-WATCH/CREATE/MODIFY/
  CONSUME stay empty
- persist a sealed change digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after S3
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
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
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    WATCH_TOOL_PROVIDER,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    watch_tool_descriptor,
)

SCHEMA_VERSION = 1
WATCH_ACTUATION_ID = "capability.watch-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-watch"
SENTINEL = "BH-WATCH-OK"
DEFAULT_TOKEN = "blackhole-watch-secret"
DEFAULT_RELPATH = "beacons/token"
SEALED_NAME = "sealed.json"
TOKEN_NAME = ".watch-token"
POLL_INTERVAL = 0.015
EVENT_TIMEOUT = 2.5

WATCH_ACTUATION_DONE_WHEN = (
    f"capability_exists:{WATCH_ACTUATION_ID};"
    f"capability_proved:{WATCH_ACTUATION_ID};"
    "no_skill_route"
)
WATCH_ACTUATION_GOAL = (
    "Repair path-watch change actuation: Unbound has no first-party filesystem "
    "mutation observer, so a WATCH/CREATE/MODIFY/CONSUME cycle never seals a "
    "change digest an independent reader can re-open. A missing watch root stays "
    "forbidden; fail-closed routing never opts the watch provider in."
)


class WatchActuationError(RuntimeError):
    """Raised when the path-watch session or observer fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def beacon_create_body(token: str = SENTINEL) -> bytes:
    return str(token or SENTINEL).encode("utf-8")


def beacon_modify_body(token: str = SENTINEL) -> bytes:
    return f"{token or SENTINEL}\n{UNLOCK_TOKEN}".encode("utf-8")


@dataclass(frozen=True)
class WatchEvent:
    action: str
    relpath: str
    digest: str
    size: int
    mtime_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "relpath": self.relpath,
            "digest": self.digest,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
        }


def _scan_beacons(root: Path) -> dict[str, tuple[int, int, str]]:
    found: dict[str, tuple[int, int, str]] = {}
    beacon_root = Path(root) / "beacons"
    if not beacon_root.is_dir():
        return found
    for path in sorted(beacon_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.suffix == ".tmp":
            continue
        relpath = path.relative_to(root).as_posix()
        data = path.read_bytes()
        stat = path.stat()
        found[relpath] = (int(stat.st_mtime_ns), int(stat.st_size), payload_sha256(data))
    return found


class PathWatchObserver:
    """Independent filesystem observer: the writer never records events itself."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.events: list[WatchEvent] = []
        self.backend = "snapshot-poll"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot: dict[str, tuple[int, int, str]] = {}

    def start(self) -> None:
        self._snapshot = _scan_beacons(self.root)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="path-watch-poll", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(POLL_INTERVAL):
            self._tick()

    def _tick(self) -> None:
        try:
            current = _scan_beacons(self.root)
        except OSError:
            return
        with self._lock:
            previous = self._snapshot
            for relpath, meta in current.items():
                if relpath not in previous:
                    self.events.append(
                        WatchEvent("create", relpath, meta[2], meta[1], meta[0])
                    )
                elif previous[relpath] != meta:
                    self.events.append(
                        WatchEvent("modify", relpath, meta[2], meta[1], meta[0])
                    )
            for relpath in previous:
                if relpath not in current:
                    self.events.append(WatchEvent("delete", relpath, "", 0, 0))
            self._snapshot = current

    def wait_for(self, action: str, relpath: str, *, timeout: float = EVENT_TIMEOUT) -> WatchEvent | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                for event in self.events:
                    if event.action == action and event.relpath == relpath:
                        return event
            self._tick()
            time.sleep(POLL_INTERVAL)
        return None

    def snapshot_events(self) -> list[WatchEvent]:
        with self._lock:
            return list(self.events)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1)


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(bytes(body))
    tmp.replace(path)


class WatchSession:
    """Token-gated on-disk path watch: bind, publish, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_TOKEN, with_root: bool = True) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.watch_root = self.output_dir / ("root" if with_root else "absent-root")
        if with_root:
            self.watch_root.mkdir(parents=True, exist_ok=True)
            (self.watch_root / "beacons").mkdir(parents=True, exist_ok=True)
        self.observer: PathWatchObserver | None = None
        self.delivered = False
        self.last_digest = ""
        self.last_token = ""
        self.history: list[dict[str, Any]] = []

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    @property
    def beacon_path(self) -> Path:
        return self.watch_root / DEFAULT_RELPATH

    @property
    def token_path(self) -> Path:
        return self.watch_root / TOKEN_NAME

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "delivered": self.delivered,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "delivered": self.delivered,
        }

    def bind(self, *, authenticate: bool = True, token: str | None = None) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
        if not self.watch_root.is_dir():
            return self._forbidden("missing_root")
        if not authenticate:
            return self._forbidden("auth_required")
        presented = self.secret if token is None else str(token)
        if presented != self.secret:
            return self._forbidden("auth_failed")
        if self.observer is not None:
            return {
                "ok": True,
                "status": 200,
                "root": str(self.watch_root),
                "reused": True,
                "backend": self.observer.backend,
            }
        self.token_path.write_text(self.secret + "\n", encoding="utf-8")
        observer = PathWatchObserver(self.watch_root)
        observer.start()
        self.observer = observer
        return {
            "ok": True,
            "status": 200,
            "root": str(self.watch_root),
            "reused": False,
            "backend": observer.backend,
        }

    def publish(
        self,
        token: str = SENTINEL,
        *,
        authenticate: bool = True,
        create: bool = True,
        modify: bool = True,
        consume: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        if self.observer is None:
            return self._conflict("watch_required")
        if not self.secret:
            return self._forbidden("missing_secret")
        if not authenticate:
            return self._forbidden("auth_required")
        presented = self.secret if secret is None else str(secret)
        if presented != self.secret:
            return self._forbidden("auth_failed")
        live_token = str(token or SENTINEL)
        relpath = DEFAULT_RELPATH
        try:
            if not create:
                return self._conflict("create_required")
            created_body = beacon_create_body(live_token)
            _atomic_write(self.beacon_path, created_body)
            created = self.observer.wait_for("create", relpath)
            if created is None:
                return self._forbidden("observer_failed", status=503)
            if not modify:
                return self._conflict("modify_required")
            modified_body = beacon_modify_body(live_token)
            _atomic_write(self.beacon_path, modified_body)
            modified = self.observer.wait_for("modify", relpath)
            if modified is None:
                return self._forbidden("observer_failed", status=503)
            if not consume:
                return self._conflict("consume_required")
            events = [event.to_dict() for event in self.observer.snapshot_events()]
            live_digest = payload_sha256(self.beacon_path.read_bytes())
            if live_digest != modified.digest:
                return self._forbidden("payload_mismatch", status=409)
            backend = self.observer.backend
            sealed = {
                "root": str(self.watch_root),
                "relpath": relpath,
                "beacon_path": str(self.beacon_path),
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": live_digest,
                "backend": backend,
                "authenticated": True,
                "watched": True,
                "created": True,
                "modified": True,
                "consumed": True,
                "independent": True,
                "events": events,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_digest = live_digest
            live = independent_watch_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "root": str(self.watch_root),
                "relpath": relpath,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": live_digest,
                "path": str(self.sealed_path),
                "backend": backend,
                "authenticated": True,
                "watched": True,
                "created": True,
                "modified": True,
                "consumed": True,
                "independent": True,
            }
        except (OSError, WatchActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "digest": "",
            }

    def read(self) -> dict[str, Any]:
        live = independent_watch_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "root": str(live.get("root") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        observer = self.observer
        self.observer = None
        if observer is not None:
            observer.stop()
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_watch_tool(session: WatchSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one watch tool call against a bound path-watch session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    create = arguments.get("create")
    if create is None:
        create = True
    modify = arguments.get("modify")
    if modify is None:
        modify = True
    consume = arguments.get("consume")
    if consume is None:
        consume = True
    secret = arguments.get("secret")
    if action == "bind":
        result = session.bind(
            authenticate=bool(authenticate),
            token=None if secret is None else str(secret),
        )
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            create=bool(create),
            modify=bool(modify),
            consume=bool(consume),
            secret=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise WatchActuationError(f"unsupported watch action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_watch_digest(sealed_path: Path) -> dict[str, Any]:
    """Re-hash the beacon file through a fresh open and compare the sealed digest."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "root": "",
    }
    if not path.is_file():
        return empty
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {**empty, "error": "invalid_payload", "detail": str(error)}
    if not isinstance(payload, dict):
        return {**empty, "error": "invalid_payload"}
    token = str(payload.get("token") or "")
    digest = str(payload.get("digest") or "")
    beacon_path = Path(str(payload.get("beacon_path") or ""))
    live_digest = ""
    if beacon_path.is_file():
        live_digest = payload_sha256(beacon_path.read_bytes())
    authenticated = payload.get("authenticated") is True
    watched = payload.get("watched") is True
    created = payload.get("created") is True
    modified = payload.get("modified") is True
    consumed = payload.get("consumed") is True
    independent = payload.get("independent") is True
    matched = bool(digest) and digest == live_digest
    sentinel = (
        SENTINEL
        if token == SENTINEL
        and matched
        and authenticated
        and watched
        and created
        and modified
        and consumed
        and independent
        else ""
    )
    return {
        "ok": bool(sentinel) and matched,
        "token": token,
        "sentinel": sentinel,
        "digest": digest,
        "live_digest": live_digest,
        "root": str(payload.get("root") or ""),
        "relpath": str(payload.get("relpath") or ""),
        "backend": str(payload.get("backend") or ""),
        "authenticated": authenticated,
        "watched": watched,
        "created": created,
        "modified": modified,
        "consumed": consumed,
        "independent": independent,
        "error": "" if sentinel else "digest_mismatch",
    }


def run_watch_workflow(
    *,
    with_secret: bool = True,
    with_root: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    create: bool = True,
    modify: bool = True,
    consume: bool = True,
    secret: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the WATCH/CREATE/MODIFY/CONSUME workflow and seal a trace."""

    descriptor = watch_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WATCH_TOOL_PROVIDER),
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
        raise WatchActuationError(f"watch tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="watch-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = WatchSession(
        out,
        secret=DEFAULT_TOKEN if with_secret else "",
        with_root=with_root,
    )
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        bind_args: dict[str, Any] = {"action": "bind", "authenticate": authenticate}
        if secret is not None:
            bind_args["secret"] = secret
        calls.append(bind_args)
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "create": create,
        "modify": modify,
        "consume": consume,
    }
    if secret is not None:
        publish_args["secret"] = secret
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_watch_tool(session, arguments))
            except WatchActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_watch_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and with_root
        and not skip_bind
        and authenticate
        and create
        and modify
        and consume
        and secret is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "watch_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "with_root": with_root,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "create": create,
        "modify": modify,
        "consume": consume,
        "wrong_secret": secret is not None,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "digest": str(publish_result.get("digest") or session.last_digest),
        "backend": str(publish_result.get("backend") or independent.get("backend") or ""),
        "delivered": bool(session.delivered or publish_result.get("watched")),
        "payload_exists": session.sealed_path.is_file(),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    final = results[-1] if results else {}
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sealed_path": str(session.sealed_path),
        "sentinel": sentinel,
        "digest": str(trace_body["digest"] or ""),
        "backend": str(trace_body["backend"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "with_root": with_root,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "create": create,
        "modify": modify,
        "consume": consume,
    }


def verify_watch_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed path-watch trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = (
        independent_watch_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    )
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "delivered": trace.get("delivered") is True,
        "authenticated": independent.get("authenticated") is True,
        "watched": independent.get("watched") is True,
        "created": independent.get("created") is True,
        "modified": independent.get("modified") is True,
        "consumed": independent.get("consumed") is True,
        "independent": independent.get("independent") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "digest_matches_live": str(independent.get("digest") or "")
        == str(independent.get("live_digest") or live_row.get("live_digest") or ""),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def watch_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.watch_actuation import "
        "builtin_watch_actuation_proof; r=builtin_watch_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='watch_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_watch_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WATCH_ACTUATION_ID,
        name="First-class path-watch CREATE/MODIFY/CONSUME filesystem actuation",
        description=(
            "Missions that require a watch tool can opt the watch provider in, "
            "bind a real on-disk watch root, subscribe an independent observer, "
            "CREATE then MODIFY a beacon, CONSUME the mutation events, "
            "independently re-hash the beacon from a fresh file open, and seal "
            "digest-chained path-watch traces. Default routing stays fail-closed; "
            "a missing watch root keeps the hole falsifiable, and skip-WATCH, "
            "skip-CREATE, skip-MODIFY, or skip-CONSUME stay empty."
        ),
        kind="python",
        entry="blackhole_agent.watch_actuation:builtin_watch_actuation_proof",
        proof_command=watch_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.s3-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/watch_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required watch tool is executable after explicit provider opt-in: "
            "Unbound binds a real on-disk watch root, subscribes an independent "
            "filesystem observer, CREATE-writes a beacon, MODIFY-rewrites it, "
            "CONSUME-reads the mutation events, independently re-hashes the "
            "beacon from a fresh file open, and binds this family as the next "
            "diversity-catalog successor once S3 SigV4 PutObject/GetObject/"
            "ListObjects is proved. Missing roots, missing tokens, unsigned "
            "subscribe, wrong tokens, skip-WATCH, skip-CREATE, skip-MODIFY, and "
            "skip-CONSUME stay fail-closed."
        ),
        tags=("watch", "path-watch", "filesystem", "mutation", "observer", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T105242Z-0ace3aae",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_watch_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in path-watch actuation seals a CREATE/MODIFY digest."""

    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.imap_actuation import IMAP_ACTUATION_GOAL, IMAP_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.ldap_actuation import LDAP_ACTUATION_GOAL, LDAP_ACTUATION_ID
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.mqtt_actuation import MQTT_ACTUATION_GOAL, MQTT_ACTUATION_ID
    from blackhole_agent.postgres_actuation import POSTGRES_ACTUATION_GOAL, POSTGRES_ACTUATION_ID
    from blackhole_agent.redis_actuation import REDIS_ACTUATION_GOAL, REDIS_ACTUATION_ID
    from blackhole_agent.s3_actuation import S3_ACTUATION_GOAL, S3_ACTUATION_ID
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
    from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = WATCH_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WATCH_ACTUATION_GOAL) == (WATCH_ACTUATION_ID,)
    checks["s3_goal_is_not_watch"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    checks["postgres_goal_is_not_watch"] = leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (
        POSTGRES_ACTUATION_ID,
    )
    checks["ldap_goal_is_not_watch"] = leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    checks["dns_goal_is_not_watch"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["mqtt_goal_is_not_watch"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_watch"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (
        REDIS_ACTUATION_ID,
    )
    checks["imap_goal_is_not_watch"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_watch"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_watch"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["webhook_goal_is_not_watch"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["watch_goal_is_not_s3"] = S3_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    checks["watch_goal_is_not_postgres"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_ldap"] = LDAP_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(WATCH_ACTUATION_GOAL)
    checks["watch_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["watch_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["s3_marker_stays_s3"] = WATCH_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["postgres_marker_stays_postgres"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["ldap_marker_stays_ldap"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        LDAP_ACTUATION_GOAL
    )
    checks["dns_marker_stays_dns"] = WATCH_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["mqtt_marker_stays_mqtt"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        MQTT_ACTUATION_GOAL
    )
    checks["redis_marker_stays_redis"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        REDIS_ACTUATION_GOAL
    )
    checks["imap_marker_stays_imap"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        IMAP_ACTUATION_GOAL
    )
    checks["smtp_marker_stays_smtp"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        SMTP_ACTUATION_GOAL
    )
    checks["sqlite_marker_stays_sqlite"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["webhook_marker_stays_webhook"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_watch"] = (
        len(catalog) > 38
        and catalog[38]["id"] == WATCH_ACTUATION_ID
        and catalog[37]["id"] == S3_ACTUATION_ID
    )
    family = capability_family(WATCH_ACTUATION_GOAL)
    checks["family_is_path"] = "path" in family
    checks["family_is_watch"] = "watch" in family
    checks["family_is_change"] = "change" in family
    checks["family_is_actuation"] = "actuation" in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_s3"] = "s3" not in family
    checks["family_is_not_postgresql"] = "postgresql" not in family
    checks["family_is_not_ldap"] = "ldap" not in family
    checks["family_is_not_directory"] = "directory" not in family
    checks["family_is_not_dns"] = "dns" not in family and "nameserver" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_redis"] = "redi" not in family
    checks["family_is_not_imap"] = "imap" not in family
    checks["family_is_not_smtp"] = "smtp" not in family
    checks["family_is_not_sqlite"] = "sqlite" not in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_hmac"] = "hmac" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_git_publication"] = "git-publication" not in family
    checks["family_is_not_auth_surface"] = family != "auth" and "auth" not in family.split("/")
    create_digest = payload_sha256(beacon_create_body())
    modify_digest = payload_sha256(beacon_modify_body())
    checks["create_and_modify_digests_differ"] = create_digest != modify_digest
    checks["modify_digest_is_sha256"] = len(modify_digest) == 64
    neighbors = (
        S3_ACTUATION_GOAL,
        POSTGRES_ACTUATION_GOAL,
        LDAP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        MQTT_ACTUATION_GOAL,
        REDIS_ACTUATION_GOAL,
        IMAP_ACTUATION_GOAL,
        SMTP_ACTUATION_GOAL,
        SQLITE_ACTUATION_GOAL,
        WEBHOOK_ACTUATION_GOAL,
    )
    watch_signature = semantic_signature(WATCH_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(watch_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_watch = ToolDescriptor(name="remote_watch", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_watch)
    checks["naive_mcp_watch_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = watch_tool_descriptor()
    default_watch = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WATCH_TOOL_PROVIDER),
    )
    checks["default_watch_provider_is_unsupported"] = (
        default_watch.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{WATCH_TOOL_PROVIDER}" in default_watch.reasons
    )
    checks["opted_in_watch_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_watch],
        required_tool_names=("local_memory", "watch"),
    )
    checks["naive_preflight_missing_watch"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["watch"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "watch"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, WATCH_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "watch" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="watch-actuation-") as tmp:
        root = Path(tmp)
        missing = run_watch_workflow(with_secret=False, output_dir=root / "missing")
        missing_root = run_watch_workflow(with_root=False, output_dir=root / "missing-root")
        unauth = run_watch_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_watch_workflow(secret="wrong-token", output_dir=root / "wrong")
        skip_watch = run_watch_workflow(skip_bind=True, output_dir=root / "skip-watch")
        skip_create = run_watch_workflow(create=False, output_dir=root / "skip-create")
        skip_modify = run_watch_workflow(modify=False, output_dir=root / "skip-modify")
        skip_consume = run_watch_workflow(consume=False, output_dir=root / "skip-consume")
        live = run_watch_workflow(output_dir=root / "live")
        verify = verify_watch_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_watch_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["missing_root_is_forbidden"] = (
            missing_root["ok"] is False
            and missing_root["final_status"] == 403
            and missing_root["error"] == "missing_root"
            and missing_root["payload_exists"] is False
        )
        checks["unsigned_watch_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 403
            and unauth["error"] == "auth_required"
            and unauth["payload_exists"] is False
        )
        checks["wrong_token_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 403
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_watch_stays_empty"] = (
            skip_watch["ok"] is False
            and skip_watch["error"] == "watch_required"
            and skip_watch["final_status"] == 409
            and skip_watch["payload_exists"] is False
        )
        checks["skip_create_stays_empty"] = (
            skip_create["ok"] is False
            and skip_create["error"] == "create_required"
            and skip_create["final_status"] == 409
            and skip_create["payload_exists"] is False
        )
        checks["skip_modify_stays_empty"] = (
            skip_modify["ok"] is False
            and skip_modify["error"] == "modify_required"
            and skip_modify["final_status"] == 409
            and skip_modify["payload_exists"] is False
        )
        checks["skip_consume_stays_empty"] = (
            skip_consume["ok"] is False
            and skip_consume["error"] == "consume_required"
            and skip_consume["final_status"] == 409
            and skip_consume["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["token_root_watch_create_modify_and_consume_are_required"] = (
            missing["ok"] is False
            and missing_root["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_watch["ok"] is False
            and skip_create["ok"] is False
            and skip_modify["ok"] is False
            and skip_consume["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False
        checks["observer_recorded_backend"] = bool(str(live.get("backend") or ""))

    with tempfile.TemporaryDirectory(prefix="watch-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != WATCH_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_watch"] = (
        live_goal == WATCH_ACTUATION_GOAL
        and WATCH_ACTUATION_ID in live_done
        and live_source == "genesis_bind_watch"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_watch_actuation_capability()
    return {
        "ok": ok,
        "action": "watch_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WATCH_ACTUATION_GOAL,
        "done_when": WATCH_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
