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
  per-step outputs, and the plan digest. Preview posts ``dry_run: true``
  so the ranked program is returned without executing untrusted tools.
  Live solve posts a ``forage`` list of candidate names when that field is
  filled so an opted-in ``--forage-root`` plane can acquire a missing tool;
  preview never sends forage.
  Invoke sends
  ``Accept: text/event-stream`` so stdout and stderr appear while the
  tool still runs; a plane that only speaks JSON is still rendered.
  When the operator fills the
  bearer-token field, those mutating fetches send
  ``Authorization: Bearer`` so a token-gated plane executes; an empty
  field keeps the historical open-loopback calls. In-flight invoke/solve
  fetches use AbortController; the cancel buttons (and closing the tab)
  hang up the HTTP socket so the plane can terminate the owned tool tree;
- durable goal sessions are created, elicited, resumed, cancelled, and
  watched from the same page: ``POST /sessions`` starts a session,
  ``POST /sessions/{id}/input`` supplies pending external keys,
  ``POST /sessions/{id}/resume`` continues an interrupted session,
  ``DELETE /sessions/{id}`` cancels a running one, and
  ``GET /sessions/{id}/events`` with ``Accept: text/event-stream``
  streams live status transitions so awaiting-input sessions no longer
  stall without a custom HTTP client.

The page talks only to the same origin it was served from; all fetch
targets are literal relative paths so an independent client can replay the
exact calls the page makes.
"""

from __future__ import annotations

import html
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
<h2>operator token</h2>
<p>Bearer token sent as <code>Authorization</code> on invoke, solve, session, and event-stream fetches. Leave empty when the plane is open.</p>
<input id="operator-token" type="password" autocomplete="off" placeholder="BLACKHOLE_INVOCATION_TOKEN">
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
<p>Live stdout/stderr stream while the tool runs; the JSON result follows.</p>
<p><button onclick="invokeCapability()">invoke</button> <button onclick="cancelInvoke()">cancel</button></p>
<pre id="invoke-result"></pre>
</section>
<section>
<h2>solve a declarative goal</h2>
<p>initial state (JSON object):</p>
<textarea id="solve-state" rows="3">{}</textarea>
<p>goal state keys (comma separated): <input id="solve-goal" placeholder="reversed_text"></p>
<p>forage candidates (comma-separated names under --forage-root): <input id="solve-forage" placeholder="shout-lab"></p>
<p><button onclick="solveGoal()">solve</button> <button onclick="previewSolve()">preview</button> <button onclick="cancelSolve()">cancel</button></p>
<pre id="solve-result"></pre>
</section>
<section>
<h2>goal sessions</h2>
<p>initial state (JSON object):</p>
<textarea id="session-state" rows="3">{}</textarea>
<p>goal state keys (comma separated): <input id="session-goal" placeholder="reversed_text"></p>
<p><button onclick="createSession()">create session</button></p>
<pre id="session-create-result"></pre>
<p>session id: <input id="session-id" placeholder="from create or list"></p>
<p>elicited input (JSON object of pending keys):</p>
<textarea id="session-input" rows="3">{}</textarea>
<p>
<button onclick="supplySessionInput()">supply input</button>
<button onclick="resumeSession()">resume</button>
<button onclick="cancelSession()">cancel</button>
<button onclick="watchSessionEvents()">watch events</button>
<button onclick="loadSessions()">refresh list</button>
</p>
<pre id="sessions">loading…</pre>
<pre id="session-events"></pre>
</section>
<script>
let invokeAbort = null;
let solveAbort = null;
let sessionEventAbort = null;
function operatorToken() {
  const node = document.getElementById("operator-token");
  return node ? node.value.trim() : "";
}
function withAuth(headers) {
  const token = operatorToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  return headers;
}
async function postJSON(path, body, controller) {
  const response = await fetch(path, {
    method: "POST",
    headers: withAuth({"Content-Type": "application/json"}),
    body: JSON.stringify(body),
    signal: controller ? controller.signal : undefined
  });
  return response.json();
}
function postInvoke(body, controller) {
  return postJSON("/invoke", body, controller);
}
function show(id, payload) {
  document.getElementById(id).textContent = JSON.stringify(payload, null, 2);
}
function parseGoalKeys(raw) {
  return raw.split(",").map(key => key.trim()).filter(key => key.length > 0);
}
function adoptSession(session) {
  if (!session || !session.session_id) return;
  document.getElementById("session-id").value = session.session_id;
  const pending = session.pending_keys || [];
  if (pending.length) {
    const blank = {};
    pending.forEach(key => { blank[key] = ""; });
    document.getElementById("session-input").value = JSON.stringify(blank, null, 2);
  }
}
async function loadHealth() {
  const response = await fetch("/health");
  show("health", await response.json());
}
async function loadSessions() {
  const response = await fetch("/sessions", {headers: withAuth({})});
  show("sessions", await response.json());
}
function cancelInvoke() {
  if (invokeAbort) invokeAbort.abort();
}
function cancelSolve() {
  if (solveAbort) solveAbort.abort();
}
async function invokeCapability() {
  let input;
  try { input = JSON.parse(document.getElementById("invoke-input").value); }
  catch (error) { show("invoke-result", {error: String(error)}); return; }
  cancelInvoke();
  invokeAbort = new AbortController();
  const node = document.getElementById("invoke-result");
  node.textContent = "running…";
  try {
    const invokeUrl = "/invoke";
    const response = await fetch(invokeUrl, {
      method: "POST",
      headers: withAuth({"Content-Type": "application/json", "Accept": "text/event-stream"}),
      body: JSON.stringify({
        capability_id: document.getElementById("invoke-id").value,
        input: input
      }),
      signal: invokeAbort.signal
    });
    const ctype = (response.headers.get("content-type") || "").toLowerCase();
    if (!ctype.includes("text/event-stream")) {
      show("invoke-result", await response.json());
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    const live = {output: [], result: null};
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      while (true) {
        const idx = buf.indexOf("\\n\\n");
        if (idx < 0) break;
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let eventName = "message";
        let payload = null;
        for (const line of raw.split("\\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) {
            try { payload = JSON.parse(line.slice(5).trim()); }
            catch (error) { payload = line.slice(5).trim(); }
          }
        }
        if (eventName === "output" && payload) {
          live.output.push(payload);
          node.textContent = JSON.stringify(live, null, 2);
        } else if (eventName === "result" || eventName === "error") {
          live.result = payload;
          node.textContent = JSON.stringify(live, null, 2);
        }
      }
    }
  } catch (error) {
    show("invoke-result", {error: String(error), cancelled: error.name === "AbortError"});
  }
}
async function postSolve(dryRun) {
  let state;
  try { state = JSON.parse(document.getElementById("solve-state").value); }
  catch (error) { show("solve-result", {error: String(error)}); return; }
  const goal = parseGoalKeys(document.getElementById("solve-goal").value);
  cancelSolve();
  solveAbort = new AbortController();
  const body = {initial_state: state, goal: goal};
  if (dryRun) body.dry_run = true;
  else {
    const forage = parseGoalKeys(document.getElementById("solve-forage").value);
    if (forage.length) body.forage = forage;
  }
  try {
    const result = await postJSON("/solve", body, solveAbort);
    show("solve-result", result);
  } catch (error) {
    show("solve-result", {error: String(error), cancelled: error.name === "AbortError"});
  }
}
async function solveGoal() {
  await postSolve(false);
}
async function previewSolve() {
  await postSolve(true);
}
async function createSession() {
  let state;
  try { state = JSON.parse(document.getElementById("session-state").value); }
  catch (error) { show("session-create-result", {error: String(error)}); return; }
  const goal = parseGoalKeys(document.getElementById("session-goal").value);
  const result = await postJSON("/sessions", {initial_state: state, goal: goal});
  show("session-create-result", result);
  adoptSession(result.session || {});
  if ((result.session || {}).session_id) watchSessionEvents();
  loadSessions();
}
async function supplySessionInput() {
  let input;
  try { input = JSON.parse(document.getElementById("session-input").value); }
  catch (error) { show("session-create-result", {error: String(error)}); return; }
  const id = document.getElementById("session-id").value.trim();
  const result = await postJSON(`/sessions/${id}/input`, {input: input});
  show("session-create-result", result);
  adoptSession(result.session || {});
  loadSessions();
}
async function resumeSession() {
  const id = document.getElementById("session-id").value.trim();
  const result = await postJSON(`/sessions/${id}/resume`, {});
  show("session-create-result", result);
  adoptSession(result.session || {});
  loadSessions();
}
async function cancelSession() {
  const id = document.getElementById("session-id").value.trim();
  const response = await fetch(`/sessions/${id}`, {
    method: "DELETE",
    headers: withAuth({})
  });
  const result = await response.json();
  show("session-create-result", result);
  loadSessions();
}
async function watchSessionEvents() {
  const id = document.getElementById("session-id").value.trim();
  if (!id) return;
  if (sessionEventAbort) sessionEventAbort.abort();
  sessionEventAbort = new AbortController();
  const node = document.getElementById("session-events");
  node.textContent = "watching…";
  try {
    const response = await fetch(`/sessions/${id}/events`, {
      headers: withAuth({"Accept": "text/event-stream"}),
      signal: sessionEventAbort.signal
    });
    if (!response.ok) {
      show("session-events", {status: response.status, body: await response.text()});
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    const events = [];
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      while (true) {
        const idx = buf.indexOf("\\n\\n");
        if (idx < 0) break;
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let payload = null;
        for (const line of raw.split("\\n")) {
          if (line.startsWith("data:")) {
            try { payload = JSON.parse(line.slice(5).trim()); }
            catch (error) { payload = line.slice(5).trim(); }
          }
        }
        if (payload) {
          events.push(payload);
          node.textContent = JSON.stringify(events, null, 2);
          adoptSession(payload);
          if (payload.status === "solved" || payload.status === "cancelled" || payload.status === "failed" || payload.status === "unsolvable") {
            loadSessions();
            return;
          }
        }
      }
    }
  } catch (error) {
    show("session-events", {error: String(error), cancelled: error.name === "AbortError"});
  }
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
