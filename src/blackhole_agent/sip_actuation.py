"""Drive a first-class SIP tool through RFC 3261 INVITE/200.

Tool routing already fails missions that require ``sip``: hosted SIP
plugins stay on the unsupported MCP provider, and no first-party SIP
provider is executable. Unbound therefore cannot speak INVITE, lockstep a
200 OK callid exchange over UDP SIP, independently poll the stored
dialog Call-ID, or seal a callid digest an independent later reader can re-open.

This module closes that hole:

- advertise a ``sip`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback RFC 3261 daemon
- keep a missing-callid client so the dialog Call-ID hole stays falsifiable
- refuse 200 OK until INVITE lands with a non-empty Call-ID
- independently poll the stored dialog Call-ID on a later client socket
- persist a sealed callid digest an independent reader can re-open
- bind this family as the next diversity-catalog successor after IKE
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import tempfile
import threading
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
    SIP_TOOL_PROVIDER,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    sip_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
SIP_ACTUATION_ID = "capability.sip-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "BH-SIP-OK"
POLL_TOKEN = "BH-SIP-POLL"
SEALED_NAME = "sealed.json"
IO_TIMEOUT = 2.0
SERVE_TIMEOUT = 0.2
CRLF = "\r\n"
EMPTY_CALLID = ""

SIP_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SIP_ACTUATION_ID};"
    f"capability_proved:{SIP_ACTUATION_ID};"
    "no_skill_route"
)
SIP_ACTUATION_GOAL = (
    "Repair rfc3261 sip invite/200 cycle cannot land over udp "
    "sip: hosted sip tools remain unsupported so an INVITE then 200 OK "
    "callid exchange cannot land and a sealed callid digest cannot be "
    "produced. A missing sip callid stays forbidden; fail-closed routing never "
    "opts the sip provider in. An independent later poll of the stored "
    "dialog callid keeps the hole falsifiable."
)


class SipActuationError(RuntimeError):
    """Raised when the SIP session or loopback daemon fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def request_callid(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"callid:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return f"{digest[:32]}@127.0.0.1"


def poll_callid(token: str = SENTINEL) -> str:
    digest = hashlib.sha256(f"poll:{token or SENTINEL}".encode("utf-8")).hexdigest()
    return f"{digest[:32]}@127.0.0.1"


DEFAULT_CALLID = request_callid(SENTINEL)


def parse_identity(from_header: str) -> str:
    text = str(from_header or "")
    match = re.search(r"sip:([^@>;\s]+)", text, re.IGNORECASE)
    if match:
        return str(match.group(1) or "")
    return ""


def encode_invite(
    *,
    identity: str,
    call_id: str,
    include_callid: bool = True,
) -> bytes:
    name = str(identity or "")
    live_callid = str(call_id or "") if include_callid else ""
    lines = [
        "INVITE sip:bob@127.0.0.1 SIP/2.0",
        f"Via: SIP/2.0/UDP 127.0.0.1;branch=z9hG4bK{name or 'anon'}",
        f"From: <sip:{name}@127.0.0.1>;tag={name or 'anon'}",
        "To: <sip:bob@127.0.0.1>",
    ]
    if include_callid:
        lines.append(f"Call-ID: {live_callid}")
    lines.extend(
        [
            "CSeq: 1 INVITE",
            f"Contact: <sip:{name}@127.0.0.1>",
            "Max-Forwards: 70",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    return CRLF.join(lines).encode("utf-8")


def encode_ok(
    *,
    identity: str,
    call_id: str,
    include_callid: bool = True,
) -> bytes:
    name = str(identity or "")
    live_callid = str(call_id or "") if include_callid else ""
    lines = [
        "SIP/2.0 200 OK",
        f"Via: SIP/2.0/UDP 127.0.0.1;branch=z9hG4bK{name or 'anon'}",
        f"From: <sip:{name}@127.0.0.1>;tag={name or 'anon'}",
        "To: <sip:bob@127.0.0.1>;tag=server",
    ]
    if include_callid:
        lines.append(f"Call-ID: {live_callid}")
    lines.extend(
        [
            "CSeq: 1 INVITE",
            "Contact: <sip:bob@127.0.0.1>",
            "Content-Length: 0",
            "",
            "",
        ]
    )
    return CRLF.join(lines).encode("utf-8")


def parse_message(data: bytes) -> dict[str, Any]:
    raw = bytes(data or b"").decode("utf-8", errors="replace")
    if not raw.strip():
        raise SipActuationError("short_packet")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    start = str(lines[0] or "").strip()
    if not start:
        raise SipActuationError("short_packet")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            break
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.strip().lower()
        if key and key not in headers:
            headers[key] = value.strip()
    call_id = str(headers.get("call-id") or headers.get("i") or "")
    identity = parse_identity(str(headers.get("from") or headers.get("f") or ""))
    start_upper = start.upper()
    is_invite = start_upper.startswith("INVITE ")
    is_ok = start_upper.startswith("SIP/2.0 200")
    is_response = start_upper.startswith("SIP/2.0")
    if not is_invite and not is_response:
        raise SipActuationError("illegal_method")
    return {
        "start": start,
        "is_invite": is_invite,
        "is_ok": is_ok,
        "is_response": is_response,
        "call_id": call_id,
        "identity": identity,
        "has_identity": bool(identity),
        "has_callid": bool(call_id),
        "cseq": str(headers.get("cseq") or ""),
    }


class _SipClient:
    def __init__(self, host: str, port: int, *, timeout: float = IO_TIMEOUT) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(timeout)
        self.client_port = int(self.sock.getsockname()[1])

    def close(self) -> None:
        sock = self.sock
        self.sock = None  # type: ignore[assignment]
        if sock is None:
            return
        try:
            sock.close()
        except OSError:
            pass

    def _recv(self) -> dict[str, Any]:
        try:
            payload, _addr = self.sock.recvfrom(65535)
        except (OSError, TimeoutError, socket.timeout) as error:
            raise SipActuationError("timeout") from error
        packet = parse_message(payload)
        if not packet["is_ok"] or not packet["is_response"]:
            raise SipActuationError("ok_required")
        if not packet["has_callid"]:
            raise SipActuationError("callid_required")
        return packet

    def exchange(
        self,
        packet: bytes,
        *,
        wait_invite: bool = True,
        wait_ok: bool = True,
    ) -> dict[str, Any]:
        if not wait_invite:
            raise SipActuationError("invite_required")
        self.sock.sendto(bytes(packet or b""), (self.host, self.port))
        if not wait_ok:
            raise SipActuationError("ok_required")
        reply = self._recv()
        return {
            "invite": True,
            "ok": reply,
            "call_id": str(reply.get("call_id") or ""),
            "identity": str(reply.get("identity") or ""),
        }

    def invite(
        self,
        identity: str,
        call_id: str,
        *,
        wait_invite: bool = True,
        wait_ok: bool = True,
        include_callid: bool = True,
    ) -> dict[str, Any]:
        packet = encode_invite(
            identity=identity,
            call_id=call_id,
            include_callid=include_callid,
        )
        return self.exchange(packet, wait_invite=wait_invite, wait_ok=wait_ok)


class SipSession:
    """Call-ID-gated loopback RFC 3261 daemon: bind, publish, read."""

    def __init__(
        self,
        output_dir: Path,
        *,
        callid_gate: str = DEFAULT_CALLID,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.callid_gate = str(callid_gate or "")
        self.host: str | None = None
        self.port: int | None = None
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.identity = ""
        self.call_id = EMPTY_CALLID
        self.stored = False
        self.retrieved = False
        self.replayed = False
        self.last_token = ""
        self.last_digest = ""
        self.history: list[dict[str, Any]] = []
        self._running = False
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def store_callid_once(self, identity: str, call_id: str) -> tuple[str, str]:
        with self._lock:
            name = str(identity or "")
            live = str(call_id or "")
            if not self.identity and name:
                self.identity = name
                self.call_id = live
                self.stored = True
            return str(self.identity), str(self.call_id)

    def read_callid(self) -> tuple[str, str]:
        with self._lock:
            return str(self.identity), str(self.call_id)

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "digest": "",
            "port": int(self.port or 0),
            "call_id": "",
            "callid": "",
            "stored": self.stored,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return self._forbidden(reason, status=409)

    def _callid_missing(self) -> bool:
        return not str(self.callid_gate or "").strip()

    def _reply_ok(self, peer: tuple[str, int], identity: str, call_id: str) -> None:
        sock = self.sock
        if sock is None:
            return
        packet = encode_ok(identity=identity, call_id=call_id)
        try:
            sock.sendto(packet, peer)
        except OSError:
            return

    def _serve(self) -> None:
        while self._running:
            sock = self.sock
            if sock is None:
                return
            try:
                payload, addr = sock.recvfrom(65535)
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                return
            try:
                packet = parse_message(payload)
            except SipActuationError:
                continue
            if packet.get("is_response"):
                continue
            if not packet.get("is_invite"):
                continue
            if not packet.get("has_callid"):
                continue
            identity = str(packet.get("identity") or "")
            if not identity:
                continue
            stored_name, stored_callid = self.store_callid_once(
                identity,
                str(packet.get("call_id") or ""),
            )
            if not stored_name or not stored_callid:
                continue
            peer = (str(addr[0]), int(addr[1]))
            with self._lock:
                self.retrieved = True
            self._reply_ok(peer, stored_name, stored_callid)

    def bind(self) -> dict[str, Any]:
        if self._callid_missing():
            return self._forbidden("missing_callid")
        if self.sock is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(SERVE_TIMEOUT)
        host, port = sock.getsockname()[:2]
        self.sock = sock
        self.host = str(host)
        self.port = int(port)
        self._running = True
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        self.thread = thread
        return {
            "ok": True,
            "status": 200,
            "host": self.host,
            "port": self.port,
            "reused": False,
        }

    def publish(
        self,
        token: str = SENTINEL,
        *,
        do_invite: bool = True,
        do_ok: bool = True,
        replay: bool = True,
        use_callid: bool = True,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if self._callid_missing():
            return self._forbidden("missing_callid")
        live_token = str(token or SENTINEL)
        origin_callid = request_callid(live_token)
        client: _SipClient | None = None
        independent: _SipClient | None = None
        try:
            client = _SipClient(self.host, int(self.port))
            if not do_invite:
                return self._conflict("invite_required")
            packet = encode_invite(
                identity=live_token,
                call_id=origin_callid,
                include_callid=use_callid,
            )
            if not use_callid:
                try:
                    client.exchange(packet, wait_invite=True, wait_ok=True)
                except SipActuationError:
                    return self._conflict("callid_required")
                return self._conflict("callid_required")
            if not do_ok:
                try:
                    client.exchange(packet, wait_invite=True, wait_ok=False)
                except SipActuationError as error:
                    if str(error) == "ok_required":
                        return self._conflict("ok_required")
                    return self._conflict("ok_required")
                return self._conflict("ok_required")
            try:
                reply = client.exchange(packet, wait_invite=True, wait_ok=True)
            except SipActuationError as error:
                reason = str(error)
                if reason == "timeout":
                    return self._conflict("callid_required")
                if reason == "invite_required":
                    return self._conflict("invite_required")
                if reason == "ok_required":
                    return self._conflict("ok_required")
                return self._conflict("invite_required")
            if str(reply.get("identity") or "") != live_token:
                return self._conflict("invite_required")
            if str(reply.get("call_id") or "") != origin_callid:
                return self._conflict("ok_required")
            self.retrieved = True
            if replay:
                independent = _SipClient(self.host, int(self.port))
                try:
                    poll = independent.invite(
                        POLL_TOKEN,
                        poll_callid(live_token),
                        wait_invite=True,
                        wait_ok=True,
                    )
                except SipActuationError:
                    return self._conflict("replay_required")
                stored_name, stored_callid = self.read_callid()
                if (
                    str(poll.get("identity") or "") != live_token
                    or stored_name != live_token
                    or stored_callid != origin_callid
                    or str(poll.get("call_id") or "") != origin_callid
                ):
                    return self._conflict("replay_required")
                self.replayed = True
            else:
                return self._conflict("replay_required")
            digest = payload_sha256(f"{origin_callid}:{live_token}".encode("utf-8"))
            sealed = {
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "call_id": origin_callid,
                "invite": True,
                "ok_response": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "callid_bound": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.last_token = live_token
            self.last_digest = digest
            live = independent_sip_digest(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "digest": digest,
                "size": len(live_token.encode("utf-8")),
                "port": int(self.port or 0),
                "call_id": origin_callid,
                "callid": origin_callid,
                "client_port": int(client.client_port),
                "path": str(self.sealed_path),
                "invite": True,
                "ok_landed": True,
                "stored": True,
                "retrieved": True,
                "replayed": True,
                "independent": True,
                "callid_bound": True,
            }
        except (OSError, SipActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "digest": "",
            }
        finally:
            if independent is not None:
                independent.close()
            if client is not None:
                client.close()

    def read(self) -> dict[str, Any]:
        live = independent_sip_digest(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "digest": str(live.get("digest") or ""),
            "call_id": str(live.get("call_id") or ""),
            "callid": str(live.get("call_id") or ""),
            "port": int(live.get("port") or 0),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        self._running = False
        sock = self.sock
        thread = self.thread
        self.sock = None
        self.thread = None
        self.host = None
        self.port = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_sip_tool(session: SipSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one SIP tool call against a bound daemon session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    do_invite = True if arguments.get("invite") is None else bool(arguments.get("invite"))
    do_ok = True if arguments.get("ok") is None else bool(arguments.get("ok"))
    replay = True if arguments.get("replay") is None else bool(arguments.get("replay"))
    use_callid = True if arguments.get("use_callid") is None else bool(arguments.get("use_callid"))
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            do_invite=do_invite,
            do_ok=do_ok,
            replay=replay,
            use_callid=use_callid,
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise SipActuationError(f"unsupported sip action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_sip_digest(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed SIP callid digest through a fresh file open."""

    path = Path(sealed_path)
    empty = {
        "ok": False,
        "error": "missing_payload",
        "token": "",
        "sentinel": "",
        "digest": "",
        "call_id": "",
        "port": 0,
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
    flags = all(
        payload.get(name) is True
        for name in (
            "invite",
            "ok_response",
            "stored",
            "retrieved",
            "replayed",
            "independent",
            "callid_bound",
        )
    )
    port = int(payload.get("port") or 0)
    call_id = str(payload.get("call_id") or "")
    dual = port > 0 and bool(call_id)
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and flags and dual else "",
        "digest": str(payload.get("digest") or ""),
        "call_id": call_id,
        "size": int(payload.get("size") or 0),
        "port": port,
        "invite": payload.get("invite") is True,
        "ok_response": payload.get("ok_response") is True,
        "stored": payload.get("stored") is True,
        "retrieved": payload.get("retrieved") is True,
        "replayed": payload.get("replayed") is True,
        "independent": payload.get("independent") is True,
        "callid_bound": payload.get("callid_bound") is True,
    }


def run_sip_workflow(
    *,
    with_callid: bool = True,
    skip_bind: bool = False,
    do_invite: bool = True,
    do_ok: bool = True,
    replay: bool = True,
    use_callid: bool = True,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the RFC 3261 INVITE/200 workflow."""

    descriptor = sip_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIP_TOOL_PROVIDER),
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
        raise SipActuationError(f"sip tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="sip-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = SipSession(out, callid_gate=DEFAULT_CALLID if with_callid else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    calls.append(
        {
            "action": "publish",
            "token": SENTINEL,
            "invite": do_invite,
            "ok": do_ok,
            "replay": replay,
            "use_callid": use_callid,
        }
    )
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_sip_tool(session, arguments))
            except SipActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_sip_digest(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_callid
        and not skip_bind
        and do_invite
        and do_ok
        and replay
        and use_callid
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sip_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_callid": with_callid,
        "skip_bind": skip_bind,
        "invite": do_invite,
        "ok": do_ok,
        "replay": replay,
        "use_callid": use_callid,
        "sealed_path": str(session.sealed_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "digest": str(publish_result.get("digest") or independent.get("digest") or ""),
        "port": int(publish_result.get("port") or independent.get("port") or 0),
        "call_id_value": str(publish_result.get("call_id") or independent.get("call_id") or ""),
        "stored": bool(session.stored or publish_result.get("stored")),
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
        "port": int(trace_body["port"] or 0),
        "call_id": str(trace_body["call_id_value"] or ""),
        "callid": str(trace_body["call_id_value"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "stored": bool(trace_body["stored"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_callid": with_callid,
        "skip_bind": skip_bind,
        "invite": do_invite,
        "ok_cycle": do_ok,
        "replay": replay,
        "use_callid": use_callid,
    }


def verify_sip_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SIP trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_sip_digest(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
    port = int(trace.get("port") or independent.get("port") or 0)
    call_id = str(trace.get("call_id_value") or independent.get("call_id") or "")
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_payload_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "payload_exists": bool(trace.get("payload_exists")) and sealed_path.is_file(),
        "stored": trace.get("stored") is True,
        "invite": independent.get("invite") is True,
        "ok_response": independent.get("ok_response") is True,
        "stored_flag": independent.get("stored") is True,
        "retrieved": independent.get("retrieved") is True,
        "replayed": independent.get("replayed") is True,
        "independent": independent.get("independent") is True,
        "callid_bound": independent.get("callid_bound") is True,
        "digest_recorded": bool(str(trace.get("digest") or independent.get("digest") or "")),
        "callid_recorded": port > 0 and call_id == DEFAULT_CALLID,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def sip_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.sip_actuation import "
        "builtin_sip_actuation_proof; r=builtin_sip_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='sip_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_sip_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SIP_ACTUATION_ID,
        name="First-class RFC 3261 SIP INVITE/200 actuation",
        description=(
            "Missions that require a sip tool can opt the sip provider in, "
            "bind a loopback RFC 3261 UDP SIP daemon, complete INVITE with a "
            "non-empty Call-ID, lockstep a 200 OK that carries the stored "
            "dialog Call-ID, independently poll the stored dialog Call-ID on a later "
            "socket, and seal a digest-chained callid. Default routing stays "
            "fail-closed; a missing callid keeps the hole falsifiable, and "
            "skip-INVITE/200/REPLAY stay empty."
        ),
        kind="python",
        entry="blackhole_agent.sip_actuation:builtin_sip_actuation_proof",
        proof_command=sip_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.ike-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/sip_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/stun_actuation.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required sip tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback RFC 3261 daemon, speaks INVITE then "
            "200 OK over UDP SIP with a non-empty Call-ID, independently "
            "polls the stored dialog Call-ID on a later client socket, and binds "
            "this family as the next diversity-catalog successor once RFC 7296 "
            "IKE lockstep is proved. Missing Call-IDs, skip-INVITE, skip-200 OK, "
            "skip-REPLAY, and INVITE aimed without a Call-ID stay "
            "fail-closed. Later genesis can take RFC 5389 STUN Binding "
            "Request/Success as the next unsaturated diversity-catalog family."
        ),
        tags=("sip", "rfc3261", "udp", "callid", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T213218Z-33e2f6e0",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_sip_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in RFC 3261 SIP lockstep actuation seals a callid digest."""

    from blackhole_agent.dhcp_actuation import DHCP_ACTUATION_GOAL, DHCP_ACTUATION_ID
    from blackhole_agent.dns_actuation import DNS_ACTUATION_GOAL, DNS_ACTUATION_ID
    from blackhole_agent.ftp_actuation import FTP_ACTUATION_GOAL, FTP_ACTUATION_ID
    from blackhole_agent.ike_actuation import IKE_ACTUATION_GOAL, IKE_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )
    from blackhole_agent.ntp_actuation import NTP_ACTUATION_GOAL, NTP_ACTUATION_ID
    from blackhole_agent.radius_actuation import RADIUS_ACTUATION_GOAL, RADIUS_ACTUATION_ID
    from blackhole_agent.snmp_actuation import SNMP_ACTUATION_GOAL, SNMP_ACTUATION_ID
    from blackhole_agent.stun_actuation import STUN_ACTUATION_GOAL, STUN_ACTUATION_ID
    from blackhole_agent.syslog_actuation import SYSLOG_ACTUATION_GOAL, SYSLOG_ACTUATION_ID
    from blackhole_agent.tftp_actuation import TFTP_ACTUATION_GOAL, TFTP_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SIP_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SIP_ACTUATION_GOAL) == (SIP_ACTUATION_ID,)
    checks["ike_goal_is_not_sip"] = leftover_marker_ids(IKE_ACTUATION_GOAL) == (IKE_ACTUATION_ID,)
    checks["dhcp_goal_is_not_sip"] = leftover_marker_ids(DHCP_ACTUATION_GOAL) == (DHCP_ACTUATION_ID,)
    checks["radius_goal_is_not_sip"] = leftover_marker_ids(RADIUS_ACTUATION_GOAL) == (RADIUS_ACTUATION_ID,)
    checks["ntp_goal_is_not_sip"] = leftover_marker_ids(NTP_ACTUATION_GOAL) == (NTP_ACTUATION_ID,)
    checks["syslog_goal_is_not_sip"] = leftover_marker_ids(SYSLOG_ACTUATION_GOAL) == (SYSLOG_ACTUATION_ID,)
    checks["snmp_goal_is_not_sip"] = leftover_marker_ids(SNMP_ACTUATION_GOAL) == (SNMP_ACTUATION_ID,)
    checks["tftp_goal_is_not_sip"] = leftover_marker_ids(TFTP_ACTUATION_GOAL) == (TFTP_ACTUATION_ID,)
    checks["ftp_goal_is_not_sip"] = leftover_marker_ids(FTP_ACTUATION_GOAL) == (FTP_ACTUATION_ID,)
    checks["dns_goal_is_not_sip"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["stun_goal_is_not_sip"] = leftover_marker_ids(STUN_ACTUATION_GOAL) == (STUN_ACTUATION_ID,)
    checks["sip_goal_is_not_ike"] = IKE_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_dhcp"] = DHCP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_radius"] = RADIUS_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_ntp"] = NTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_syslog"] = SYSLOG_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_snmp"] = SNMP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_tftp"] = TFTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_ftp"] = FTP_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["sip_goal_is_not_stun"] = STUN_ACTUATION_ID not in leftover_marker_ids(SIP_ACTUATION_GOAL)
    checks["ike_marker_stays_ike"] = SIP_ACTUATION_ID not in leftover_marker_ids(IKE_ACTUATION_GOAL)
    checks["dhcp_marker_stays_dhcp"] = SIP_ACTUATION_ID not in leftover_marker_ids(DHCP_ACTUATION_GOAL)
    checks["radius_marker_stays_radius"] = SIP_ACTUATION_ID not in leftover_marker_ids(RADIUS_ACTUATION_GOAL)
    checks["ntp_marker_stays_ntp"] = SIP_ACTUATION_ID not in leftover_marker_ids(NTP_ACTUATION_GOAL)
    checks["syslog_marker_stays_syslog"] = SIP_ACTUATION_ID not in leftover_marker_ids(SYSLOG_ACTUATION_GOAL)
    checks["snmp_marker_stays_snmp"] = SIP_ACTUATION_ID not in leftover_marker_ids(SNMP_ACTUATION_GOAL)
    checks["tftp_marker_stays_tftp"] = SIP_ACTUATION_ID not in leftover_marker_ids(TFTP_ACTUATION_GOAL)
    checks["ftp_marker_stays_ftp"] = SIP_ACTUATION_ID not in leftover_marker_ids(FTP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = SIP_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["stun_marker_stays_stun"] = SIP_ACTUATION_ID not in leftover_marker_ids(STUN_ACTUATION_GOAL)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_sip"] = (
        len(catalog) > 53
        and catalog[53]["id"] == SIP_ACTUATION_ID
        and catalog[52]["id"] == IKE_ACTUATION_ID
        and catalog[53]["source"] == "genesis_bind_sip"
    )
    checks["catalog_names_stun"] = (
        len(catalog) > 54
        and catalog[54]["id"] == STUN_ACTUATION_ID
        and catalog[54]["source"] == "genesis_bind_stun"
    )
    family = capability_family(SIP_ACTUATION_GOAL)
    checks["family_is_sip"] = "sip" in family
    checks["family_is_rfc3261"] = "rfc3261" in family
    checks["family_is_callid"] = "callid" in family
    checks["family_is_not_ike"] = "ike" not in family and "rfc7296" not in family and "spi" not in family
    checks["family_is_not_dhcp"] = "dhcp" not in family and "rfc2131" not in family and "yiaddr" not in family
    checks["family_is_not_radius"] = (
        "radius" not in family and "radiu" not in family and "rfc2865" not in family
    )
    checks["family_is_not_ntp"] = "ntp" not in family and "rfc5905" not in family and "keyid" not in family
    checks["family_is_not_syslog"] = "syslog" not in family and "nilvalue" not in family
    checks["family_is_not_snmp"] = "snmp" not in family and "varbind" not in family
    checks["family_is_not_tftp"] = "tftp" not in family and "rfc1350" not in family
    checks["family_is_not_ftp"] = "ftpd" not in family and "pasv" not in family
    checks["family_is_not_dns"] = "tsig" not in family and "nameserver" not in family
    checks["family_is_not_stun"] = "stun" not in family and "rfc5389" not in family and "txid" not in family
    packed = encode_invite(identity=SENTINEL, call_id=DEFAULT_CALLID)
    parsed = parse_message(packed)
    checks["invite_roundtrip"] = (
        parsed["is_invite"] is True
        and parsed["identity"] == SENTINEL
        and parsed["has_identity"] is True
        and parsed["has_callid"] is True
        and parsed["call_id"] == DEFAULT_CALLID
        and parsed["is_response"] is False
        and parsed["is_ok"] is False
    )
    ok_packet = encode_ok(identity=SENTINEL, call_id=DEFAULT_CALLID)
    ok_parsed = parse_message(ok_packet)
    checks["ok_roundtrip"] = (
        ok_parsed["is_ok"] is True
        and ok_parsed["identity"] == SENTINEL
        and ok_parsed["call_id"] == DEFAULT_CALLID
        and ok_parsed["is_response"] is True
        and ok_parsed["is_invite"] is False
    )
    bare = encode_invite(identity=SENTINEL, call_id=DEFAULT_CALLID, include_callid=False)
    checks["missing_callid_is_unauthenticated"] = parse_message(bare)["has_callid"] is False
    neighbors = (
        IKE_ACTUATION_GOAL,
        DHCP_ACTUATION_GOAL,
        RADIUS_ACTUATION_GOAL,
        NTP_ACTUATION_GOAL,
        SYSLOG_ACTUATION_GOAL,
        SNMP_ACTUATION_GOAL,
        TFTP_ACTUATION_GOAL,
        FTP_ACTUATION_GOAL,
        DNS_ACTUATION_GOAL,
        STUN_ACTUATION_GOAL,
    )
    sip_signature = semantic_signature(SIP_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(sip_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_sip = ToolDescriptor(name="remote_sip", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_sip)
    checks["naive_mcp_sip_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = sip_tool_descriptor()
    default_sip = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIP_TOOL_PROVIDER),
    )
    checks["default_sip_provider_is_unsupported"] = (
        default_sip.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SIP_TOOL_PROVIDER}" in default_sip.reasons
    )
    checks["opted_in_sip_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_sip],
        required_tool_names=("local_memory", "sip"),
    )
    checks["naive_preflight_missing_sip"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["sip"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "sip"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SIP_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "sip" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="sip-actuation-") as tmp:
        root = Path(tmp)
        missing = run_sip_workflow(with_callid=False, output_dir=root / "missing")
        skip_bind = run_sip_workflow(skip_bind=True, output_dir=root / "skip-bind")
        skip_invite = run_sip_workflow(do_invite=False, output_dir=root / "skip-invite")
        skip_ok = run_sip_workflow(do_ok=False, output_dir=root / "skip-ok")
        skip_replay = run_sip_workflow(replay=False, output_dir=root / "skip-replay")
        skip_callid = run_sip_workflow(use_callid=False, output_dir=root / "skip-callid")
        live = run_sip_workflow(output_dir=root / "live")
        verify = verify_sip_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_sip_trace(clone)
        checks["naive_without_callid_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_callid"
            and missing["payload_exists"] is False
        )
        checks["skip_bind_stays_empty"] = (
            skip_bind["ok"] is False
            and skip_bind["error"] == "not_bound"
            and skip_bind["final_status"] == 409
            and skip_bind["payload_exists"] is False
        )
        checks["skip_invite_stays_empty"] = (
            skip_invite["ok"] is False
            and skip_invite["error"] == "invite_required"
            and skip_invite["final_status"] == 409
            and skip_invite["payload_exists"] is False
        )
        checks["skip_ok_stays_empty"] = (
            skip_ok["ok"] is False
            and skip_ok["error"] == "ok_required"
            and skip_ok["final_status"] == 409
            and skip_ok["payload_exists"] is False
        )
        checks["skip_replay_stays_empty"] = (
            skip_replay["ok"] is False
            and skip_replay["error"] == "replay_required"
            and skip_replay["final_status"] == 409
            and skip_replay["payload_exists"] is False
        )
        checks["skip_callid_stays_empty"] = (
            skip_callid["ok"] is False
            and skip_callid["error"] == "callid_required"
            and skip_callid["final_status"] == 409
            and skip_callid["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_digest"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["workflow_records_callid"] = live.get("call_id") == DEFAULT_CALLID and int(live.get("port") or 0) > 0
        checks["token_callid_invite_ok_and_replay_are_required"] = (
            missing["ok"] is False
            and skip_bind["ok"] is False
            and skip_invite["ok"] is False
            and skip_ok["ok"] is False
            and skip_replay["ok"] is False
            and skip_callid["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="sip-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SIP_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_sip"] = (
        live_goal == SIP_ACTUATION_GOAL
        and SIP_ACTUATION_ID in live_done
        and live_source == "genesis_bind_sip"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_sip_actuation_capability()
    return {
        "ok": ok,
        "action": "sip_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SIP_ACTUATION_GOAL,
        "done_when": SIP_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
