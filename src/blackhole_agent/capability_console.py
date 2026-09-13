"""Operator console: a self-contained browser page for the invocation plane.

Every surface of the capability service so far is a machine protocol: JSON
endpoints (``/invoke``, ``/solve``, ``/sessions``) or the MCP stdio server.
An operator with only a browser has no way to see what the plane can do or
to drive it. This module closes that gap with a single self-contained HTML
document served at ``GET /console`` (and ``/``):

- the live invocable catalog is embedded at render time (capability id,
  name, requires/provides contract), so the page shows real ledger data
  even before any script runs;
- inline JavaScript (no external assets, no CDN, no build step) refreshes
  ``/health``, ``/capabilities`` and ``/sessions``, invokes any selected
  capability through ``POST /invoke`` with a JSON input form, and submits
  declarative goals through ``POST /solve``, rendering the derived plan,
  per-step outputs, and the plan digest;
- durable goal sessions are listed with their status so an operator can
  see in-flight, awaiting-input, solved, failed, and cancelled goals.

The page talks only to the same origin it was served from; all fetch
targets are literal relative paths so an independent client can replay the
exact calls the page makes.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from blackhole_agent.capability_service import capability_listing

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>blackhole capability console</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; background: #101418; color: #d7dde3; }
h1, h2 { color: #7fd4ff; }
section { border: 1px solid #2a323b; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
td, th { border: 1px solid #2a323b; padding: 0.25rem 0.5rem; text-align: left; vertical-align: top; }
textarea, input { width: 100%; background: #0b0e11; color: #d7dde3; border: 1px solid #2a323b; border-radius: 4px; font-family: monospace; }
button { background: #1f6feb; color: white; border: 0; border-radius: 4px; padding: 0.4rem 1rem; cursor: pointer; }
pre { background: #0b0e11; padding: 0.75rem; border-radius: 4px; overflow: auto; }
.ok { color: #6fdc8c; } .err { color: #ff8489; }
</style>
</head>
<body>
<h1>blackhole capability console</h1>
<section>
<h2>service health</h2>
<pre id="health">loading…</pre>
</section>
<section>
<h2>invocable catalog (<span id="count">__COUNT__</span>, listing digest <code>__DIGEST__</code>)</h2>
<table id="catalog">
<thead><tr><th>capability</th><th>name</th><th>requires</th><th>provides</th></tr></thead>
<tbody>
__ROWS__
</tbody>
</table>
</section>
<section>
<h2>invoke a capability</h2>
<p>capability id: <input id="invoke-id" list="cap-ids" placeholder="capability.absorbed-…"><datalist id="cap-ids">__OPTIONS__</datalist></p>
<p>input (JSON object):</p>
<textarea id="invoke-input" rows="3">{}</textarea>
<p><button onclick="invokeCapability()">invoke</button></p>
<pre id="invoke-result"></pre>
</section>
<section>
<h2>solve a declarative goal</h2>
<p>initial state (JSON object):</p>
<textarea id="solve-state" rows="3">{}</textarea>
<p>goal state keys (comma separated): <input id="solve-goal" placeholder="reversed_text"></p>
<p><button onclick="solveGoal()">solve</button></p>
<pre id="solve-result"></pre>
</section>
<section>
<h2>goal sessions</h2>
<pre id="sessions">loading…</pre>
<p><button onclick="loadSessions()">refresh</button></p>
</section>
<script>
async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  return response.json();
}
function show(id, payload) {
  document.getElementById(id).textContent = JSON.stringify(payload, null, 2);
}
async function loadHealth() {
  const response = await fetch("/health");
  show("health", await response.json());
}
async function loadSessions() {
  const response = await fetch("/sessions");
  show("sessions", await response.json());
}
async function invokeCapability() {
  let input;
  try { input = JSON.parse(document.getElementById("invoke-input").value); }
  catch (error) { show("invoke-result", {error: String(error)}); return; }
  const result = await postJSON("/invoke", {
    capability_id: document.getElementById("invoke-id").value,
    input: input
  });
  show("invoke-result", result);
}
async function solveGoal() {
  let state;
  try { state = JSON.parse(document.getElementById("solve-state").value); }
  catch (error) { show("solve-result", {error: String(error)}); return; }
  const goal = document.getElementById("solve-goal").value.split(",")
    .map(key => key.trim()).filter(key => key.length > 0);
  const result = await postJSON("/solve", {initial_state: state, goal: goal});
  show("solve-result", result);
}
loadHealth();
loadSessions();
</script>
</body>
</html>
"""


def console_html(root: Path) -> str:
    """Render the operator console against the live invocable catalog."""

    listing: dict[str, Any] = capability_listing(Path(root).resolve())
    capabilities = listing.get("capabilities") or []
    rows: list[str] = []
    options: list[str] = []
    for item in capabilities:
        capability_id = html.escape(str(item.get("id") or ""))
        name = html.escape(str(item.get("name") or ""))
        requires = html.escape(", ".join(str(key) for key in item.get("requires") or []))
        provides = html.escape(", ".join(str(key) for key in item.get("provides") or []))
        rows.append(
            f"<tr><td><code>{capability_id}</code></td><td>{name}</td>"
            f"<td>{requires}</td><td>{provides}</td></tr>"
        )
        options.append(f'<option value="{capability_id}">')
    page = _PAGE.replace("__COUNT__", str(listing.get("count") or 0))
    page = page.replace("__DIGEST__", html.escape(str(listing.get("listing_digest") or ""))[:16])
    page = page.replace("__ROWS__", "\n".join(rows))
    page = page.replace("__OPTIONS__", "".join(options))
    return page
