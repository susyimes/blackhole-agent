"""Poll a changing, paginated repository feed from four separate processes."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from blackhole_agent import github_growth as growth

START = datetime(2026, 1, 9, 12, tzinfo=timezone.utc)
# Each list is a page. None means the server failed on that page.
SCANS = [
    (0, {
        "active": [[("newest", -1), ("known", -6)], [("newest", -1), ("tie", -1), ("legacy-late", -20)]],
        "quiet": [[]],
    }),
    (180, {
        "active": [[("recent", 160), ("late", -35), ("expired", -61)]],
        "quiet": [[("during-outage", 30)], None],
    }),
    (240, {
        "active": [[("recent", 160), ("boundary", 120), ("expired-again", 119)]],
        "quiet": [[("during-outage", 30)], [("during-outage", 30), ("quiet-late", -59), ("too-old", -61)]],
    }),
]


class RepositoryFeed(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/search/repositories":
            self.send_response(200)
            payload = {"total_count": 0, "items": []}
        else:
            pages = self.server.feeds[url.path.split("/")[-2]]
            page = int(parse_qs(url.query).get("page", ["1"])[0])
            rows = pages[page - 1]
            if rows is None:
                self.send_error(503)
                return
            self.send_response(200)
            if page < len(pages):
                next_url = f"http://127.0.0.1:{self.server.server_port}{url.path}?page={page + 1}"
                self.send_header("Link", f'<{next_url}>; rel="next"')
            payload = [
                {"id": name, "type": "ReleaseEvent", "created_at": (START + timedelta(minutes=offset)).isoformat(),
                 "payload": {"action": "published", "release": {"tag_name": name}}}
                for name, offset in rows
            ]
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *_):
        pass


def poll(root, port, minute):
    with requests.Session() as session, patch.object(growth, "datetime", wraps=datetime) as clock:
        session.trust_env = False
        clock.now.return_value = START + timedelta(minutes=minute)
        growth.run_intake_once(
            repos=["fixture/active", "fixture/quiet"], output_dir=root, repo_path=root,
            client=growth.GitHubEventsClient(session=session, api_base_url=f"http://127.0.0.1:{port}"),
            trend_config=growth.GitHubTrendConfig(), proposal_mode="heuristic", lookback_hours=1,
        )


def observe(root):
    (root / "state.json").write_text(json.dumps({
        "seen_event_ids": ["known"],
        "last_seen_at_by_repo": {"fixture/active": (START - timedelta(minutes=6)).isoformat()},
    }), encoding="utf-8")
    items, errors = [], []
    with HTTPServer(("127.0.0.1", 0), RepositoryFeed) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for minute, feeds in [*SCANS, (241, SCANS[-1][1])]:
                server.feeds = feeds
                command = [sys.executable, __file__, str(root), str(server.server_port), str(minute)]
                subprocess.run(command, check=True, timeout=25)
                digest = json.loads((root / "latest.json").read_bytes())
                items.append([row["item_id"] for row in digest["items"]])
                errors.append([row["repo"] for row in digest["source"]["event_fetch_errors"]])
        finally:
            server.shutdown()
            worker.join()
    return {"items": items, "failed_feeds": errors}


EXPECTED = {
    "items": [["newest", "tie", "legacy-late"], ["recent", "late"], ["boundary", "during-outage", "quiet-late"], []],
    "failed_feeds": [[], ["fixture/quiet"], [], []],
}


def test_restarted_polls(tmp_path):
    assert observe(tmp_path) == EXPECTED


if __name__ == "__main__":
    if len(sys.argv) == 4:
        poll(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
    else:
        with TemporaryDirectory() as directory:
            observed = observe(Path(directory))
        print(json.dumps({"passed": observed == EXPECTED, "observed": observed}))
