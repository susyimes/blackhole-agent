"""Drive a first-class S3 tool through SigV4 object-store PUT/GET/LIST.

Tool routing already fails missions that require ``s3``: hosted bucket-object
plugins stay on the unsupported MCP provider, and no first-party S3 provider
is executable. Unbound therefore cannot speak AWS4-HMAC-SHA256, PutObject,
GetObject, ListObjects, or seal an ETag an independent reader can re-GET.

This module closes that hole:

- advertise an ``s3`` provider tool that stays fail-closed until opted in
- drive bind / publish / read against a real loopback path-style listener
- keep a missing-secret client so the SigV4 hole stays falsifiable
- refuse GetObject/ListObjects until PutObject succeeds under SigV4
- GET after PUT, LIST the bucket, then independently re-GET from a fresh
  signed request so skip-PUT, skip-GET, and skip-LIST stay empty
- persist a sealed object etag an independent reader can re-open
- bind this family as the next diversity-catalog successor after PostgreSQL
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    S3_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    s3_tool_descriptor,
)

SCHEMA_VERSION = 1
S3_ACTUATION_ID = "capability.s3-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-s3"
SENTINEL = "BH-S3-OK"
DEFAULT_ACCESS_KEY = "BLACKHOLE"
DEFAULT_SECRET = "blackhole-s3-secret"
DEFAULT_REGION = "us-east-1"
DEFAULT_SERVICE = "s3"
DEFAULT_BUCKET = "blackhole"
DEFAULT_KEY = "beacons/token"
SEALED_NAME = "sealed.json"
LIST_QUERY = "list-type=2"
AUTH_ALGO = "AWS4-HMAC-SHA256"
SIGNED_HEADERS = "host;x-amz-content-sha256;x-amz-date"

S3_ACTUATION_DONE_WHEN = (
    f"capability_exists:{S3_ACTUATION_ID};"
    f"capability_proved:{S3_ACTUATION_ID};"
    "no_skill_route"
)
S3_ACTUATION_GOAL = (
    "Repair object-store bucket PutObject: hosted s3 tools remain "
    "unsupported so a SigV4/PutObject/GetObject/ListObjects cycle cannot "
    "land and a sealed object etag cannot be produced. A missing s3 secret "
    "stays forbidden; fail-closed routing never opts the s3 provider in."
)


class S3ActuationError(RuntimeError):
    """Raised when the S3 session or listener fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def amz_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def payload_sha256(body: bytes) -> str:
    return hashlib.sha256(bytes(body or b"")).hexdigest()


def object_etag(body: bytes) -> str:
    return f'"{payload_sha256(body)}"'


def object_path(bucket: str = DEFAULT_BUCKET, key: str = DEFAULT_KEY) -> str:
    return f"/{bucket}/{key}"


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, datestamp: str, region: str = DEFAULT_REGION, service: str = DEFAULT_SERVICE) -> bytes:
    k_date = _hmac(f"AWS4{secret}".encode("utf-8"), datestamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    return _hmac(k_service, "aws4_request")


def aws4_sign(
    *,
    method: str,
    canonical_uri: str,
    canonical_query: str,
    host: str,
    payload: bytes,
    secret: str,
    access_key: str = DEFAULT_ACCESS_KEY,
    amz_date: str | None = None,
    region: str = DEFAULT_REGION,
    service: str = DEFAULT_SERVICE,
) -> dict[str, str]:
    """Return AWS4-HMAC-SHA256 headers for a path-style S3 request."""

    live_date = str(amz_date or amz_now())
    hashed = payload_sha256(payload)
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{hashed}\nx-amz-date:{live_date}\n"
    canonical_request = "\n".join(
        (
            method.upper(),
            canonical_uri,
            canonical_query,
            canonical_headers,
            SIGNED_HEADERS,
            hashed,
        )
    )
    datestamp = live_date[:8]
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        (
            AUTH_ALGO,
            live_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        )
    )
    signature = hmac.new(
        signing_key(secret, datestamp, region, service),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"{AUTH_ALGO} Credential={access_key}/{scope}, "
        f"SignedHeaders={SIGNED_HEADERS}, Signature={signature}"
    )
    return {
        "authorization": authorization,
        "payload_hash": hashed,
        "signature": signature,
        "canonical_request": canonical_request,
        "string_to_sign": string_to_sign,
        "amz_date": live_date,
        "scope": scope,
        "host": host,
    }


def parse_authorization(header: str) -> dict[str, str]:
    text = str(header or "").strip()
    if not text.startswith(f"{AUTH_ALGO} "):
        return {}
    fields: dict[str, str] = {}
    for item in text[len(AUTH_ALGO) + 1 :].split(","):
        piece = item.strip()
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        fields[key.strip()] = value.strip()
    credential = str(fields.get("Credential") or "")
    parts = credential.split("/")
    if len(parts) >= 5:
        fields["access_key"] = parts[0]
        fields["datestamp"] = parts[1]
        fields["region"] = parts[2]
        fields["service"] = parts[3]
        fields["scope"] = "/".join(parts[1:])
    return fields


def verify_aws4(
    *,
    method: str,
    canonical_uri: str,
    canonical_query: str,
    host: str,
    payload: bytes,
    authorization: str,
    amz_date: str,
    payload_hash: str,
    secret: str,
) -> dict[str, Any]:
    """Recompute SigV4 and compare with compare_digest."""

    fields = parse_authorization(authorization)
    signature = str(fields.get("Signature") or "")
    if not signature or not secret:
        return {"ok": False, "error": "auth_required", "signature": ""}
    expected_hash = payload_sha256(payload)
    if payload_hash and not hmac.compare_digest(payload_hash, expected_hash):
        return {"ok": False, "error": "auth_failed", "signature": ""}
    signed = aws4_sign(
        method=method,
        canonical_uri=canonical_uri,
        canonical_query=canonical_query,
        host=host,
        payload=payload,
        secret=secret,
        access_key=str(fields.get("access_key") or DEFAULT_ACCESS_KEY),
        amz_date=amz_date,
        region=str(fields.get("region") or DEFAULT_REGION),
        service=str(fields.get("service") or DEFAULT_SERVICE),
    )
    matched = hmac.compare_digest(signed["signature"], signature)
    return {
        "ok": matched,
        "error": "" if matched else "auth_failed",
        "signature": signed["signature"],
        "provided": signature,
    }


def encode_list_xml(bucket: str, objects: Mapping[str, bytes]) -> bytes:
    contents = []
    for key, body in objects.items():
        etag = object_etag(body)
        contents.append(
            f"<Contents><Key>{key}</Key><ETag>{etag}</ETag><Size>{len(body)}</Size></Contents>"
        )
    inner = "".join(contents)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<ListBucketResult><Name>{bucket}</Name>{inner}</ListBucketResult>"
    ).encode("utf-8")


def parse_list_keys(payload: bytes) -> list[str]:
    try:
        root = ET.fromstring(payload.decode("utf-8"))
    except (UnicodeDecodeError, ET.ParseError):
        return []
    keys: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "Key" and node.text:
            keys.append(str(node.text))
    return keys


def encode_error_xml(code: str, message: str) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<Error><Code>{code}</Code><Message>{message}</Message></Error>"
    ).encode("utf-8")


def parse_error_message(payload: bytes) -> str:
    try:
        root = ET.fromstring(payload.decode("utf-8"))
    except (UnicodeDecodeError, ET.ParseError):
        return ""
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "Message" and node.text:
            return str(node.text)
    return ""


def split_object_path(path: str) -> tuple[str, str]:
    stripped = str(path or "").split("?", 1)[0].strip("/")
    if not stripped:
        return "", ""
    if "/" not in stripped:
        return stripped, ""
    bucket, key = stripped.split("/", 1)
    return bucket, key


def s3_http(
    method: str,
    url: str,
    *,
    body: bytes = b"",
    headers: Mapping[str, str] | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=body if body else None,
        headers=dict(headers or {}),
        method=method.upper(),
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "ok": 200 <= int(response.status) < 300,
                "status": int(response.status),
                "body": raw,
                "etag": str(response.headers.get("ETag") or ""),
                "error": "",
            }
    except urllib.error.HTTPError as error:
        raw = error.read() if error.fp is not None else b""
        message = parse_error_message(raw) or "http_error"
        return {
            "ok": False,
            "status": int(error.code),
            "body": raw,
            "etag": str(error.headers.get("ETag") if error.headers else "") or "",
            "error": message,
        }
    except urllib.error.URLError as error:
        return {
            "ok": False,
            "status": 503,
            "body": b"",
            "etag": "",
            "error": "unreachable",
            "detail": str(error.reason),
        }


class _S3HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], session: S3Session) -> None:
        self.session = session
        super().__init__(address, handler)


class _S3Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        return

    def _send(self, status: int, body: bytes, *, content_type: str = "application/xml", etag: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _authorize(self, method: str, canonical_uri: str, canonical_query: str, payload: bytes) -> str:
        session: S3Session = self.server.session  # type: ignore[attr-defined]
        authorization = str(self.headers.get("Authorization") or "")
        if not authorization:
            return "auth_required"
        host = str(self.headers.get("Host") or "")
        amz_date = str(self.headers.get("X-Amz-Date") or "")
        payload_hash = str(self.headers.get("X-Amz-Content-Sha256") or "")
        checked = verify_aws4(
            method=method,
            canonical_uri=canonical_uri,
            canonical_query=canonical_query,
            host=host,
            payload=payload,
            authorization=authorization,
            amz_date=amz_date,
            payload_hash=payload_hash,
            secret=session.secret,
        )
        return "" if checked.get("ok") else str(checked.get("error") or "auth_failed")

    def _deny(self, reason: str) -> None:
        code = "AccessDenied" if reason in {"auth_required", "auth_failed"} else "InvalidRequest"
        status = 403 if reason in {"auth_required", "auth_failed"} else 400
        self._send(status, encode_error_xml(code, reason))

    def do_PUT(self) -> None:  # noqa: N802 - stdlib
        session: S3Session = self.server.session  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        payload = self._read_body()
        denied = self._authorize("PUT", parsed.path, parsed.query, payload)
        if denied:
            self._deny(denied)
            return
        bucket, key = split_object_path(parsed.path)
        if bucket != session.bucket or not key:
            self._send(400, encode_error_xml("InvalidBucketName", "bad_path"))
            return
        etag = session.put_object(key, payload)
        self._send(200, b"", etag=etag)

    def do_GET(self) -> None:  # noqa: N802 - stdlib
        session: S3Session = self.server.session  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        payload = self._read_body()
        denied = self._authorize("GET", parsed.path, parsed.query, payload)
        if denied:
            self._deny(denied)
            return
        bucket, key = split_object_path(parsed.path)
        if bucket != session.bucket:
            self._send(404, encode_error_xml("NoSuchBucket", "missing_bucket"))
            return
        if parsed.query == LIST_QUERY or (not key and "list-type=2" in parsed.query):
            body = encode_list_xml(session.bucket, session.list_objects())
            self._send(200, body)
            return
        if not key:
            self._send(400, encode_error_xml("InvalidRequest", "missing_key"))
            return
        stored = session.get_object(key)
        if stored is None:
            self._send(404, encode_error_xml("NoSuchKey", "missing_object"))
            return
        self._send(200, stored, content_type="application/octet-stream", etag=object_etag(stored))


class _S3Client:
    """Minimal path-style S3 client with AWS4-HMAC-SHA256."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        secret: str,
        access_key: str = DEFAULT_ACCESS_KEY,
        timeout: float = 6.0,
    ) -> None:
        self.host = str(host)
        self.port = int(port)
        self.secret = str(secret)
        self.access_key = str(access_key)
        self.timeout = timeout
        self.host_header = f"{self.host}:{self.port}"
        self.base = f"http://{self.host}:{self.port}"

    def call(
        self,
        method: str,
        canonical_uri: str,
        *,
        query: str = "",
        body: bytes = b"",
        signed: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        payload = bytes(body or b"")
        amz_date = amz_now()
        headers = {
            "Host": self.host_header,
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_sha256(payload),
        }
        if signed:
            key = self.secret if secret is None else str(secret)
            if not key:
                return {"ok": False, "status": 403, "body": b"", "etag": "", "error": "missing_secret"}
            signed_headers = aws4_sign(
                method=method,
                canonical_uri=canonical_uri,
                canonical_query=query,
                host=self.host_header,
                payload=payload,
                secret=key,
                access_key=self.access_key,
                amz_date=amz_date,
            )
            headers["Authorization"] = signed_headers["authorization"]
            headers["X-Amz-Content-Sha256"] = signed_headers["payload_hash"]
        url = self.base + canonical_uri
        if query:
            url = f"{url}?{query}"
        return s3_http(method, url, body=payload, headers=headers, timeout=self.timeout)

    def put(self, key: str, body: bytes, **kwargs: Any) -> dict[str, Any]:
        return self.call("PUT", object_path(DEFAULT_BUCKET, key), body=body, **kwargs)

    def get(self, key: str, **kwargs: Any) -> dict[str, Any]:
        return self.call("GET", object_path(DEFAULT_BUCKET, key), **kwargs)

    def list_bucket(self, **kwargs: Any) -> dict[str, Any]:
        return self.call("GET", f"/{DEFAULT_BUCKET}", query=LIST_QUERY, **kwargs)


class S3Session:
    """Credential-gated loopback S3 object store: bind, publish, read."""

    def __init__(self, output_dir: Path, *, secret: str = DEFAULT_SECRET) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.secret = str(secret or "")
        self.access_key = DEFAULT_ACCESS_KEY
        self.bucket = DEFAULT_BUCKET
        self.host: str | None = None
        self.port: int | None = None
        self.server: _S3HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.delivered = False
        self.last_token = ""
        self.last_etag = ""
        self.history: list[dict[str, Any]] = []
        self._objects: dict[str, bytes] = {}
        self._lock = threading.Lock()

    @property
    def sealed_path(self) -> Path:
        return self.output_dir / SEALED_NAME

    def put_object(self, key: str, body: bytes) -> str:
        payload = bytes(body)
        with self._lock:
            self._objects[str(key)] = payload
        return object_etag(payload)

    def get_object(self, key: str) -> bytes | None:
        with self._lock:
            stored = self._objects.get(str(key))
            return None if stored is None else bytes(stored)

    def list_objects(self) -> dict[str, bytes]:
        with self._lock:
            return {key: bytes(value) for key, value in self._objects.items()}

    def _forbidden(self, reason: str, *, status: int = 403) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": reason,
            "token": "",
            "sentinel": "",
            "etag": "",
            "delivered": self.delivered,
        }

    def _conflict(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 409,
            "error": reason,
            "token": "",
            "sentinel": "",
            "etag": "",
            "delivered": self.delivered,
        }

    def bind(self) -> dict[str, Any]:
        if not self.secret:
            return self._forbidden("missing_secret")
        if self.server is not None:
            return {
                "ok": True,
                "status": 200,
                "host": self.host or "",
                "port": int(self.port or 0),
                "reused": True,
            }
        server = _S3HTTPServer(("127.0.0.1", 0), _S3Handler, self)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        self.server = server
        self.thread = thread
        self.host = str(host)
        self.port = int(port)
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
        authenticate: bool = True,
        put: bool = True,
        get: bool = True,
        list_bucket: bool = True,
        secret: str | None = None,
    ) -> dict[str, Any]:
        if self.port is None or self.host is None:
            return self._conflict("not_bound")
        if not self.secret:
            return self._forbidden("missing_secret")
        live_token = str(token or SENTINEL)
        body = live_token.encode("utf-8")
        writer = _S3Client(self.host, int(self.port), secret=self.secret, access_key=self.access_key)
        try:
            if not put:
                return self._conflict("put_required")
            stored = writer.put(
                DEFAULT_KEY,
                body,
                signed=bool(authenticate),
                secret=None if secret is None else str(secret),
            )
            if not stored.get("ok"):
                reason = str(stored.get("error") or "auth_failed")
                if reason == "missing_secret":
                    return self._forbidden("missing_secret")
                if not authenticate or reason == "auth_required":
                    return self._forbidden("auth_required")
                return self._forbidden("auth_failed")
            if not get:
                return self._conflict("get_required")
            fetched = writer.get(DEFAULT_KEY)
            if not fetched.get("ok"):
                return self._forbidden("get_failed", status=404)
            fetched_body = bytes(fetched.get("body") or b"")
            if fetched_body != body:
                return self._forbidden("payload_mismatch", status=409)
            etag = str(fetched.get("etag") or object_etag(fetched_body))
            if not list_bucket:
                return self._conflict("list_required")
            listed = writer.list_bucket()
            if not listed.get("ok"):
                return self._forbidden("list_failed", status=404)
            keys = parse_list_keys(bytes(listed.get("body") or b""))
            if DEFAULT_KEY not in keys:
                return self._forbidden("list_required", status=409)
            independent = _S3Client(self.host, int(self.port), secret=self.secret, access_key=self.access_key)
            replay = independent.get(DEFAULT_KEY)
            replay_body = bytes(replay.get("body") or b"")
            if not replay.get("ok") or replay_body != body:
                return self._forbidden("independent_required", status=409)
            sealed = {
                "bucket": self.bucket,
                "key": DEFAULT_KEY,
                "token": live_token,
                "sentinel": SENTINEL if live_token == SENTINEL else "",
                "etag": etag,
                "authenticated": True,
                "put": True,
                "got": True,
                "listed": True,
                "independent": True,
                "received_at": utc_now_iso(),
            }
            self.sealed_path.write_text(_canonical(sealed) + "\n", encoding="utf-8")
            self.delivered = True
            self.last_token = live_token
            self.last_etag = etag
            live = independent_s3_object(self.sealed_path)
            return {
                "ok": True,
                "status": 200,
                "queued": False,
                "object_store": True,
                "bucket": self.bucket,
                "key": DEFAULT_KEY,
                "token": live_token,
                "sentinel": str(live.get("sentinel") or ""),
                "etag": etag,
                "path": str(self.sealed_path),
                "authenticated": True,
                "put": True,
                "got": True,
                "listed": True,
                "independent": True,
            }
        except (OSError, S3ActuationError) as error:
            return {
                "ok": False,
                "status": 503,
                "error": "unreachable",
                "detail": str(error),
                "token": live_token,
                "sentinel": "",
                "etag": "",
            }

    def read(self) -> dict[str, Any]:
        live = independent_s3_object(self.sealed_path)
        return {
            "ok": bool(live.get("ok")),
            "status": 200 if live.get("ok") else 404,
            "token": str(live.get("token") or ""),
            "sentinel": str(live.get("sentinel") or ""),
            "etag": str(live.get("etag") or ""),
            "bucket": str(live.get("bucket") or ""),
            "path": str(self.sealed_path),
            "error": str(live.get("error") or ""),
        }

    def close(self) -> dict[str, Any]:
        server = self.server
        thread = self.thread
        self.server = None
        self.thread = None
        self.host = None
        self.port = None
        if server is not None:
            try:
                server.shutdown()
            except OSError:
                pass
            try:
                server.server_close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=1)
        return {"ok": True, "status": 200, "closed": True, "path": str(self.sealed_path)}


def call_s3_tool(session: S3Session, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one S3 tool call against a bound object-store session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    authenticate = arguments.get("authenticate")
    if authenticate is None:
        authenticate = True
    put = arguments.get("put")
    if put is None:
        put = True
    get = arguments.get("get")
    if get is None:
        get = True
    list_bucket = arguments.get("list_bucket")
    if list_bucket is None:
        list_bucket = True
    secret = arguments.get("secret")
    if action == "bind":
        result = session.bind()
    elif action == "publish":
        result = session.publish(
            token,
            authenticate=bool(authenticate),
            put=bool(put),
            get=bool(get),
            list_bucket=bool(list_bucket),
            secret=None if secret is None else str(secret),
        )
    elif action == "read":
        result = session.read()
    elif action == "close":
        result = session.close()
    else:
        raise S3ActuationError(f"unsupported s3 action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_s3_object(sealed_path: Path) -> dict[str, Any]:
    """Read the sealed S3 object etag through a fresh file open."""

    path = Path(sealed_path)
    if not path.is_file():
        return {
            "ok": False,
            "error": "missing_payload",
            "token": "",
            "sentinel": "",
            "etag": "",
            "bucket": "",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "error": "invalid_payload",
            "detail": str(error),
            "token": "",
            "sentinel": "",
            "etag": "",
            "bucket": "",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "invalid_payload",
            "token": "",
            "sentinel": "",
            "etag": "",
            "bucket": "",
        }
    token = str(payload.get("token") or "")
    authenticated = payload.get("authenticated") is True
    put = payload.get("put") is True
    got = payload.get("got") is True
    listed = payload.get("listed") is True
    independent = payload.get("independent") is True
    return {
        "ok": True,
        "token": token,
        "sentinel": SENTINEL if token == SENTINEL and authenticated and put and got and listed and independent else "",
        "etag": str(payload.get("etag") or ""),
        "bucket": str(payload.get("bucket") or ""),
        "key": str(payload.get("key") or ""),
        "authenticated": authenticated,
        "put": put,
        "got": got,
        "listed": listed,
        "independent": independent,
    }


def run_s3_workflow(
    *,
    with_secret: bool = True,
    skip_bind: bool = False,
    authenticate: bool = True,
    put: bool = True,
    get: bool = True,
    list_bucket: bool = True,
    secret: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the SigV4/PutObject/GetObject/ListObjects workflow and seal a trace."""

    descriptor = s3_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, S3_TOOL_PROVIDER),
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
        raise S3ActuationError(f"s3 tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="s3-live-"))
    out.mkdir(parents=True, exist_ok=True)
    session = S3Session(out, secret=DEFAULT_SECRET if with_secret else "")
    calls: list[dict[str, Any]] = []
    if not skip_bind:
        calls.append({"action": "bind"})
    publish_args: dict[str, Any] = {
        "action": "publish",
        "token": SENTINEL,
        "authenticate": authenticate,
        "put": put,
        "get": get,
        "list_bucket": list_bucket,
    }
    if secret is not None:
        publish_args["secret"] = secret
    calls.append(publish_args)
    calls.extend([{"action": "read"}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_s3_tool(session, arguments))
            except S3ActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    read_result = next((item for item in results if item.get("action") == "read"), {})
    publish_result = next((item for item in results if item.get("action") == "publish"), {})
    independent = independent_s3_object(session.sealed_path)
    sentinel = str(read_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and with_secret
        and not skip_bind
        and authenticate
        and put
        and get
        and list_bucket
        and secret is None
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and session.sealed_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "s3_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "put": put,
        "get": get,
        "list_bucket": list_bucket,
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
        "etag": str(publish_result.get("etag") or session.last_etag),
        "delivered": bool(session.delivered or publish_result.get("object_store")),
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
        "etag": str(trace_body["etag"] or ""),
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or publish_result.get("error") or ""),
        "delivered": bool(trace_body["delivered"]),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "payload_exists": session.sealed_path.is_file(),
        "with_secret": with_secret,
        "skip_bind": skip_bind,
        "authenticate": authenticate,
        "put": put,
        "get": get,
        "list_bucket": list_bucket,
    }


def verify_s3_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed S3 object-store trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    sealed_path = Path(str(trace.get("sealed_path") or ""))
    live_row = independent_s3_object(sealed_path) if sealed_path.is_file() else {"ok": False, "sentinel": ""}
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
        "put": independent.get("put") is True,
        "got": independent.get("got") is True,
        "listed": independent.get("listed") is True,
        "independent": independent.get("independent") is True,
        "etag_recorded": bool(str(trace.get("etag") or independent.get("etag") or "")),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def s3_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.s3_actuation import "
        "builtin_s3_actuation_proof; r=builtin_s3_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='s3_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_s3_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=S3_ACTUATION_ID,
        name="First-class SigV4 PutObject/GetObject/ListObjects object-store actuation",
        description=(
            "Missions that require an s3 tool can opt the s3 provider in, bind a "
            "loopback path-style S3 listener, sign AWS4-HMAC-SHA256, PutObject a "
            "beacon, GetObject it, ListObjects the bucket, independently re-GET "
            "from a fresh signed request, and seal digest-chained object-store "
            "traces. Default routing stays fail-closed; a missing s3 secret keeps "
            "the hole falsifiable, and skip-PUT, skip-GET, or skip-LIST stay empty."
        ),
        kind="python",
        entry="blackhole_agent.s3_actuation:builtin_s3_actuation_proof",
        proof_command=s3_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.postgres-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/s3_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required s3 tool is executable after explicit provider opt-in: "
            "Unbound binds a real loopback path-style S3 listener, signs "
            "AWS4-HMAC-SHA256, PutObject-writes a beacon, GetObject-reads the "
            "ETag, ListObjects the bucket, independently re-GETs from a fresh "
            "signed request, and binds this family as the next diversity-catalog "
            "successor once PostgreSQL Startup/Password/SimpleQuery is proved. "
            "Missing secrets, unsigned PutObject, wrong signatures, skip-PUT, "
            "skip-GET, and skip-LIST stay fail-closed."
        ),
        tags=("s3", "object-store", "bucket", "sigv4", "putobject", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T101954Z-a377016a",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_s3_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in S3 actuation seals a SigV4 PUT/GET/LIST object."""

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
    from blackhole_agent.smtp_actuation import SMTP_ACTUATION_GOAL, SMTP_ACTUATION_ID
    from blackhole_agent.sqlite_actuation import SQLITE_ACTUATION_GOAL, SQLITE_ACTUATION_ID
    from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = S3_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(S3_ACTUATION_GOAL) == (S3_ACTUATION_ID,)
    checks["postgres_goal_is_not_s3"] = leftover_marker_ids(POSTGRES_ACTUATION_GOAL) == (
        POSTGRES_ACTUATION_ID,
    )
    checks["ldap_goal_is_not_s3"] = leftover_marker_ids(LDAP_ACTUATION_GOAL) == (LDAP_ACTUATION_ID,)
    checks["dns_goal_is_not_s3"] = leftover_marker_ids(DNS_ACTUATION_GOAL) == (DNS_ACTUATION_ID,)
    checks["mqtt_goal_is_not_s3"] = leftover_marker_ids(MQTT_ACTUATION_GOAL) == (MQTT_ACTUATION_ID,)
    checks["redis_goal_is_not_s3"] = leftover_marker_ids(REDIS_ACTUATION_GOAL) == (REDIS_ACTUATION_ID,)
    checks["imap_goal_is_not_s3"] = leftover_marker_ids(IMAP_ACTUATION_GOAL) == (IMAP_ACTUATION_ID,)
    checks["smtp_goal_is_not_s3"] = leftover_marker_ids(SMTP_ACTUATION_GOAL) == (SMTP_ACTUATION_ID,)
    checks["sqlite_goal_is_not_s3"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (SQLITE_ACTUATION_ID,)
    checks["webhook_goal_is_not_s3"] = leftover_marker_ids(WEBHOOK_ACTUATION_GOAL) == (
        WEBHOOK_ACTUATION_ID,
    )
    checks["s3_goal_is_not_postgres"] = POSTGRES_ACTUATION_ID not in leftover_marker_ids(
        S3_ACTUATION_GOAL
    )
    checks["s3_goal_is_not_ldap"] = LDAP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_dns"] = DNS_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_mqtt"] = MQTT_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_redis"] = REDIS_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_imap"] = IMAP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_smtp"] = SMTP_ACTUATION_ID not in leftover_marker_ids(S3_ACTUATION_GOAL)
    checks["s3_goal_is_not_sqlite"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        S3_ACTUATION_GOAL
    )
    checks["s3_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        S3_ACTUATION_GOAL
    )
    checks["postgres_marker_stays_postgres"] = S3_ACTUATION_ID not in leftover_marker_ids(
        POSTGRES_ACTUATION_GOAL
    )
    checks["ldap_marker_stays_ldap"] = S3_ACTUATION_ID not in leftover_marker_ids(LDAP_ACTUATION_GOAL)
    checks["dns_marker_stays_dns"] = S3_ACTUATION_ID not in leftover_marker_ids(DNS_ACTUATION_GOAL)
    checks["mqtt_marker_stays_mqtt"] = S3_ACTUATION_ID not in leftover_marker_ids(MQTT_ACTUATION_GOAL)
    checks["redis_marker_stays_redis"] = S3_ACTUATION_ID not in leftover_marker_ids(
        REDIS_ACTUATION_GOAL
    )
    checks["imap_marker_stays_imap"] = S3_ACTUATION_ID not in leftover_marker_ids(IMAP_ACTUATION_GOAL)
    checks["smtp_marker_stays_smtp"] = S3_ACTUATION_ID not in leftover_marker_ids(SMTP_ACTUATION_GOAL)
    checks["sqlite_marker_stays_sqlite"] = S3_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["webhook_marker_stays_webhook"] = S3_ACTUATION_ID not in leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_s3"] = (
        len(catalog) > 37
        and catalog[37]["id"] == S3_ACTUATION_ID
        and catalog[36]["id"] == POSTGRES_ACTUATION_ID
    )
    family = capability_family(S3_ACTUATION_GOAL)
    checks["family_is_object"] = "object" in family
    checks["family_is_store"] = "store" in family
    checks["family_is_bucket"] = "bucket" in family
    checks["family_is_putobject"] = "putobject" in family
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
    signed = aws4_sign(
        method="PUT",
        canonical_uri=object_path(),
        canonical_query="",
        host="127.0.0.1:9000",
        payload=SENTINEL.encode("utf-8"),
        secret=DEFAULT_SECRET,
        amz_date="20260901T101954Z",
    )
    verified = verify_aws4(
        method="PUT",
        canonical_uri=object_path(),
        canonical_query="",
        host="127.0.0.1:9000",
        payload=SENTINEL.encode("utf-8"),
        authorization=signed["authorization"],
        amz_date="20260901T101954Z",
        payload_hash=signed["payload_hash"],
        secret=DEFAULT_SECRET,
    )
    forged = verify_aws4(
        method="PUT",
        canonical_uri=object_path(),
        canonical_query="",
        host="127.0.0.1:9000",
        payload=SENTINEL.encode("utf-8"),
        authorization=signed["authorization"],
        amz_date="20260901T101954Z",
        payload_hash=signed["payload_hash"],
        secret="wrong-secret",
    )
    checks["sigv4_roundtrip"] = (
        verified.get("ok") is True
        and signed["signature"] == verified.get("signature")
        and AUTH_ALGO in signed["authorization"]
        and SIGNED_HEADERS in signed["authorization"]
    )
    checks["sigv4_wrong_secret_fails"] = forged.get("ok") is False and forged.get("error") == "auth_failed"
    listed = encode_list_xml(DEFAULT_BUCKET, {DEFAULT_KEY: SENTINEL.encode("utf-8")})
    checks["list_xml_roundtrip"] = parse_list_keys(listed) == [DEFAULT_KEY]
    checks["etag_is_quoted_sha256"] = object_etag(SENTINEL.encode("utf-8")) == f'"{payload_sha256(SENTINEL.encode("utf-8"))}"'
    neighbors = (
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
    s3_signature = semantic_signature(S3_ACTUATION_GOAL)
    checks["not_a_neighbor_duplicate"] = all(
        semantic_similarity(s3_signature, semantic_signature(goal)) < 0.82 for goal in neighbors
    )

    mcp_s3 = ToolDescriptor(name="remote_s3", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_s3)
    checks["naive_mcp_s3_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = s3_tool_descriptor()
    default_s3 = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, S3_TOOL_PROVIDER),
    )
    checks["default_s3_provider_is_unsupported"] = (
        default_s3.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{S3_TOOL_PROVIDER}" in default_s3.reasons
    )
    checks["opted_in_s3_is_executable"] = opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_s3],
        required_tool_names=("local_memory", "s3"),
    )
    checks["naive_preflight_missing_s3"] = (
        naive_preflight["ok"] is False and naive_preflight["missing_required_tool_names"] == ["s3"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "s3"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, S3_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "s3" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="s3-actuation-") as tmp:
        root = Path(tmp)
        missing = run_s3_workflow(with_secret=False, output_dir=root / "missing")
        unauth = run_s3_workflow(authenticate=False, output_dir=root / "unauth")
        wrong = run_s3_workflow(secret="wrong-secret", output_dir=root / "wrong")
        skip_put = run_s3_workflow(put=False, output_dir=root / "skip-put")
        skip_get = run_s3_workflow(get=False, output_dir=root / "skip-get")
        skip_list = run_s3_workflow(list_bucket=False, output_dir=root / "skip-list")
        live = run_s3_workflow(output_dir=root / "live")
        verify = verify_s3_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_s3_trace(clone)
        checks["naive_without_secret_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_secret"
            and missing["payload_exists"] is False
        )
        checks["unsigned_put_is_forbidden"] = (
            unauth["ok"] is False
            and unauth["final_status"] == 403
            and unauth["error"] == "auth_required"
            and unauth["delivered"] is False
            and unauth["payload_exists"] is False
        )
        checks["wrong_secret_is_forbidden"] = (
            wrong["ok"] is False
            and wrong["final_status"] == 403
            and wrong["error"] == "auth_failed"
            and wrong["payload_exists"] is False
        )
        checks["skip_put_stays_empty"] = (
            skip_put["ok"] is False
            and skip_put["error"] == "put_required"
            and skip_put["final_status"] == 409
            and skip_put["payload_exists"] is False
        )
        checks["skip_get_stays_empty"] = (
            skip_get["ok"] is False
            and skip_get["error"] == "get_required"
            and skip_get["final_status"] == 409
            and skip_get["payload_exists"] is False
        )
        checks["skip_list_stays_empty"] = (
            skip_list["ok"] is False
            and skip_list["error"] == "list_required"
            and skip_list["final_status"] == 409
            and skip_list["payload_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_object"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sealed_file"] = live["payload_exists"] is True
        checks["secret_signature_put_get_and_list_are_required"] = (
            missing["ok"] is False
            and unauth["ok"] is False
            and wrong["ok"] is False
            and skip_put["ok"] is False
            and skip_get["ok"] is False
            and skip_list["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="s3-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != S3_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_s3"] = (
        live_goal == S3_ACTUATION_GOAL
        and S3_ACTUATION_ID in live_done
        and live_source == "genesis_bind_s3"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_s3_actuation_capability()
    return {
        "ok": ok,
        "action": "s3_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": S3_ACTUATION_GOAL,
        "done_when": S3_ACTUATION_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }
