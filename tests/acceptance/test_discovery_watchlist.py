"""Poll a local search service and its live release feeds from fresh processes."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlsplit

import requests

from blackhole_agent import github_growth as growth


class Feed(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/search/repositories":
            if self.server.status == 0:
                return  # Drop the connection before sending the HTTP headers.
            if self.server.status == "truncated":
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b'{"items":[')
                return
            if self.server.status == "rate_limited":
                self.send_response(403)
                self.send_header("X-RateLimit-Remaining", "0")
                self.end_headers()
                return
            if self.server.status not in (200, "partial"):
                self.send_error(self.server.status)
                return
            names = self.server.names
            payload = {"total_count": len(names), "incomplete_results": self.server.status == "partial",
                       "items": [{"full_name": name, "topics": ["workflow"]} for name in names]}
        else:
            name = path.removeprefix("/repos/").removesuffix("/events")
            self.server.reads.append(name)
            release = self.server.release
            payload = [{
                "id": release, "type": "ReleaseEvent", "created_at": self.server.now.isoformat(),
                "payload": {"action": "published", "release": {"tag_name": release}},
            }] if release else []
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *_):
        pass


def poll(root, url, query, token, now):
    with requests.Session() as session, patch.object(growth, "datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime.fromisoformat(now)
        session.trust_env = False
        client = growth.GitHubEventsClient(session=session, api_base_url=url, token=token)
        try:
            result = growth.run_intake_once(output_dir=root, repo_path=root, client=client,
                                            trend_config=growth.GitHubTrendConfig(query=query), proposal_mode="heuristic")
        except (RuntimeError, requests.RequestException) as error:
            return {"source": "unavailable", "items": [], "error": str(error)}
    digest = json.loads(result.json_path.read_bytes())
    source = digest["source"]
    discovered = source.get("discovered_at")
    return {
        "source": source["kind"], "items": [row["item_id"] for row in digest["items"]],
        "generated": digest["generated_at"], "discovered": discovered,
        "dated_warning": bool(source.get("search_error") and discovered
                              and discovered in result.markdown_path.read_text(encoding="utf-8")),
    }


def observe(root):
    alpha, beta = "sample/alpha", "sample/beta"
    live, cached, refused = "github_trending_repositories", "github_cached_watchlist", "unavailable"
    # Each row also specifies which feeds the peer must actually see and which items may be published.
    cases = [
        ("cold", 503, [], "", "workflow", "one", refused, [], []),
        ("prime", 200, [alpha], "", "workflow", "one", live, [alpha], ["trend:" + alpha]),
        ("outage", 503, [], "release-1", "workflow", "one", cached, [alpha], ["release-1"]),
        ("disconnect", 0, [], "release-1", "workflow", "one", cached, [alpha], []),
        ("truncated", "truncated", [], "release-1", "workflow", "one", cached, [alpha], []),
        ("partial_search", "partial", [beta], "", "workflow", "one", live, [beta], ["trend:" + beta]),
        ("rate_limit", "rate_limited", [], "release-1", "workflow", "one", cached, [alpha], []),
        ("other_query", 503, [], "", "science", "one", refused, [], []),
        ("other_token", 503, [], "", "workflow", "two", refused, [], []),
        ("denied", 403, [], "", "workflow", "one", refused, [], []),
        ("expired", 503, [], "", "workflow", "one", refused, [], []),
        ("recover", 200, [beta], "", "workflow", "one", live, [beta], ["trend:" + beta]),
        ("next_outage", 503, [], "release-2", "workflow", "one", cached, [beta], ["release-2"]),
        ("empty_search", 200, [], "", "workflow", "one", live, [], []),
        ("after_empty", 503, [], "retired", "workflow", "one", cached, [], []),
    ]
    observed, passed, last_discovery = {}, True, None
    now = datetime(2026, 7, 8, 23, 57, tzinfo=timezone.utc)
    with HTTPServer(("127.0.0.1", 0), Feed) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for label, status, names, release, query, token, source, feeds, items in cases:
                now += timedelta(days=7) if label == "expired" else timedelta(minutes=1)
                server.status, server.names, server.release, server.reads = status, names, release, []
                server.now = now
                run = subprocess.run(
                    [sys.executable, __file__, str(root), f"http://127.0.0.1:{server.server_port}", query, token, now.isoformat()],
                    capture_output=True, text=True, check=True, timeout=20,
                )
                row = json.loads(run.stdout)
                observed[label] = {"source": row["source"], "feeds": server.reads, "items": row["items"]}
                passed &= (row["source"], server.reads, row["items"]) == (source, feeds, items)
                if source == live and status == 200:
                    last_discovery = row.get("generated")
                elif source == cached:
                    observed[label]["discovered_at"] = row.get("discovered")
                    passed &= bool(last_discovery and row.get("discovered") == last_discovery and row.get("dated_warning"))
        finally:
            server.shutdown()
            worker.join()
    return {"passed": passed, "observed": observed}


def test_search_outage(tmp_path):
    result = observe(tmp_path)
    assert result["passed"], result["observed"]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(poll(Path(sys.argv[1]), *sys.argv[2:])))
    else:
        with TemporaryDirectory() as directory:
            print(json.dumps(observe(Path(directory))))
