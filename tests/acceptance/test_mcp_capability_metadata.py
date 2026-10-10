"""A host discovers metadata, prepares a call, and uses its advertised contract.

Wire fixture: MCP 2025-03-26 resources/list, resources/read, URI templates,
prompts/list and prompts/get with an embedded JSON resource, as specified at
https://modelcontextprotocol.io/specification/2025-03-26/server/resources and
https://modelcontextprotocol.io/specification/2025-03-26/server/prompts.

Uses an independent stdlib HTTP client, with no server catalog helpers or
proof routines. The baseline returns method-not-found for resource/prompt
discovery; that is an unmet outcome, not a crash. Both outcomes exit zero.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from blackhole_agent.capability_service import build_server

CAPABILITY_ID = "capability.absorbed-temperature-summary"
INDEX_URI = "blackhole://capabilities"
DETAIL_URI = INDEX_URI + "/" + CAPABILITY_ID
PROMPT_NAME = "prepare_capability_call"


def _fixture(root: Path) -> Path:
    tool = root / "capabilities" / "absorbed" / "temperature-summary"
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "values = json.load(sys.stdin)['measurements_c']\n"
        "with Path('calls.log').open('a') as log: log.write('called\\n')\n"
        "print(json.dumps({'mean_f': round(sum(values) / len(values) * 1.8 + 32, 2)}))\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "slug": "temperature-summary",
        "name": "Temperature summary",
        "command": ["python", "tool.py"],
        "requires": ["measurements_c"],
        "provides": ["mean_f"],
        "cases": [
            {"input": {"measurements_c": [0, 100]}, "expect": {"mean_f": 122.0}},
            {"input": {"measurements_c": [10, 20]}, "expect": {"mean_f": 59.0}},
        ],
    }
    (tool / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    ledger = {
        "schema_version": 1,
        "capabilities": {
            CAPABILITY_ID: {"name": "Temperature summary", "last_proof_exit_code": 0},
        },
    }
    (root / "capabilities" / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    return tool / "calls.log"


def _change_entry(root: Path, **changes) -> None:
    path = root / "capabilities" / "ledger.json"
    previous = path.stat().st_mtime_ns
    ledger = json.loads(path.read_text(encoding="utf-8"))
    ledger["capabilities"][CAPABILITY_ID].update(changes)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    os.utime(path, ns=(previous, max(path.stat().st_mtime_ns, previous + 1_000_000_000)))


class Host:
    def __init__(self, url: str) -> None:
        self.url = url
        self.session = ""
        self.serial = 0

    def rpc(self, method: str, params: dict | None = None, *, authorized: bool = True) -> dict:
        self.serial += 1
        payload = {"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params or {}}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if authorized:
            headers["Authorization"] = "Bearer metadata-probe-token"
        request = Request(self.url, json.dumps(payload).encode("utf-8"), headers, method="POST")
        try:
            with urlopen(request, timeout=40) as response:
                self.session = response.headers.get("Mcp-Session-Id", self.session)
                body = json.loads(response.read())
                assert body.get("jsonrpc") == "2.0" and body.get("id") == self.serial, body
                return body
        except HTTPError as exc:
            return {"http_status": exc.code, "body": json.loads(exc.read())}

    def result(self, method: str, params: dict | None = None) -> dict:
        reply = self.rpc(method, params)
        assert "result" in reply, {"method": method, "reply": reply}
        return reply["result"]

    def read(self, uri: str) -> tuple[dict, dict]:
        contents = self.result("resources/read", {"uri": uri})["contents"]
        assert len(contents) == 1 and contents[0]["uri"] == uri
        assert contents[0]["mimeType"] == "application/json" and isinstance(contents[0]["text"], str)
        return contents[0], json.loads(contents[0]["text"])


def main() -> dict:
    observed: dict = {"workflow": "MCP metadata discovery -> embedded prompt contract -> governed tools/call"}
    with tempfile.TemporaryDirectory(prefix="mcp-metadata-") as directory:
        root = Path(directory)
        calls = _fixture(root)
        server = build_server(root, port=0, token="metadata-probe-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host = Host(f"http://127.0.0.1:{server.server_address[1]}/mcp")
            initialized = host.result("initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "independent-metadata-host", "version": "1"},
            })
            resource_reply = host.rpc("resources/list")
            prompt_reply = host.rpc("prompts/list")
            observed["discovery"] = {"resources": resource_reply, "prompts": prompt_reply}
            if "result" not in resource_reply or "result" not in prompt_reply:
                return {"passed": False, "observed": observed}

            assert {"tools", "resources", "prompts"} <= initialized["capabilities"].keys()
            assert initialized["capabilities"]["resources"].get("subscribe", False) is False
            assert {item["uri"] for item in resource_reply["result"]["resources"]} == {INDEX_URI, DETAIL_URI}
            _, index = host.read(INDEX_URI)
            content, metadata = host.read(DETAIL_URI)
            assert index["count"] == 1 and index["capabilities"] == [metadata]
            assert metadata["requires"] == ["measurements_c"] and metadata["provides"] == ["mean_f"]
            assert metadata["available"] is True
            assert metadata["tool"] in host.result("tools/list")["tools"]
            assert metadata["tool"]["inputSchema"]["properties"]["measurements_c"]["type"] == "array"
            template = host.result("resources/templates/list")["resourceTemplates"][0]
            assert template["uriTemplate"].replace("{capability_id}", metadata["id"]) == DETAIL_URI
            prompt_descriptor = prompt_reply["result"]["prompts"][0]
            assert prompt_descriptor["name"] == PROMPT_NAME
            assert any(arg["name"] == "capability_id" and arg["required"] for arg in prompt_descriptor["arguments"])
            task = "Find the mean Fahrenheit temperature for Celsius measurements [5, 14, 23]."
            prompt = host.result("prompts/get", {
                "name": PROMPT_NAME, "arguments": {"capability_id": metadata["id"], "task": task},
            })
            assert all(message["role"] in {"user", "assistant"} for message in prompt["messages"])
            embedded = [message["content"]["resource"] for message in prompt["messages"]
                        if message["content"]["type"] == "resource"]
            assert embedded == [content]
            assert any(message["content"].get("text") == task for message in prompt["messages"])
            assert not calls.exists(), "metadata retrieval executed the capability"
            for private in ("tool_root", "proof_command", "last_proof_exit_code", '"command"', '"cases"', str(root)):
                assert private not in json.dumps(index), private
            prepared = json.loads(embedded[0]["text"])
            actual = host.result("tools/call", {
                "name": prepared["tool"]["name"], "arguments": {prepared["requires"][0]: [5, 14, 23]},
            })
            assert actual["isError"] is False
            assert actual["structuredContent"] == {prepared["provides"][0]: 57.2}
            assert calls.read_text() == "called\n"
            observed["prepared_call_output"] = actual["structuredContent"]
            observed["metadata_is_read_only"] = True

            errors = {
                "foreign_uri": host.rpc("resources/read", {"uri": "file:///etc/passwd"}),
                "path_traversal": host.rpc("resources/read", {"uri": INDEX_URI + "/%2e%2e/ledger.json"}),
                "invalid_cursor": host.rpc("resources/list", {"cursor": "bad-cursor"}),
                "missing_argument": host.rpc("prompts/get", {"name": PROMPT_NAME}),
                "nonstring_argument": host.rpc("prompts/get", {
                    "name": PROMPT_NAME, "arguments": {"capability_id": CAPABILITY_ID, "task": []},
                }),
            }
            observed["error_codes"] = {key: reply.get("error", {}).get("code") for key, reply in errors.items()}
            assert observed["error_codes"] == {
                "foreign_uri": -32002, "path_traversal": -32002, "invalid_cursor": -32602,
                "missing_argument": -32602, "nonstring_argument": -32602,
            }
            assert host.rpc("resources/read", {"uri": DETAIL_URI}, authorized=False)["http_status"] == 401
            assert host.rpc("prompts/get", {
                "name": PROMPT_NAME, "arguments": {"capability_id": CAPABILITY_ID},
            }, authorized=False)["http_status"] == 401
            observed["http_authentication_enforced"] = True

            _change_entry(root, resource_quarantine={"reason": "private resource-limit details"})
            _, quarantined = host.read(DETAIL_URI)
            assert quarantined["available"] is False and quarantined["unavailable_reason"] == "resource_quarantined"
            assert "private resource-limit details" not in json.dumps(quarantined)
            assert host.rpc("prompts/get", {
                "name": PROMPT_NAME, "arguments": {"capability_id": CAPABILITY_ID},
            })["error"]["code"] == -32602
            _, updated = host.read(INDEX_URI)
            assert updated["catalog_digest"] != index["catalog_digest"]
            _change_entry(root, last_proof_exit_code=1)
            assert [item["uri"] for item in host.result("resources/list")["resources"]] == [INDEX_URI]
            assert host.rpc("resources/read", {"uri": DETAIL_URI})["error"]["code"] == -32002
            assert calls.read_text() == "called\n"
            observed["live_quarantine_and_removal"] = True
            observed["session_still_usable"] = host.result("ping") == {}
            return {"passed": True, "observed": observed}
        except (AssertionError, KeyError, ValueError, OSError) as exc:
            observed["failure"] = f"{type(exc).__name__}: {exc}"
            return {"passed": False, "observed": observed}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    print(json.dumps(main()))
