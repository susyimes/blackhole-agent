"""Drive a first-class Godot tool through a project-gated scene workflow.

Tool routing already fails missions that require ``godot``: hosted game-engine
plugins stay on the unsupported MCP provider, and no first-party engine
provider is executable. Unbound therefore cannot open a project, mutate a
scene tree, or seal a play-check.

This module closes that hole:

- advertise a ``godot`` provider tool that stays fail-closed until opted in
- drive list / create_scene / add_node / save / run against an in-process
  Godot 4 project fixture that writes real ``project.godot`` and ``.tscn``
- keep a missing-project client so the project-open hole stays falsifiable
- refuse node mutation until a scene exists
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor after Gmail
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
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
    GODOT_TOOL_PROVIDER,
    MCP_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    godot_tool_descriptor,
    local_memory_tool_descriptor,
    route_tool_descriptor,
)

SCHEMA_VERSION = 1
GODOT_ACTUATION_ID = "capability.godot-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-godot"
SENTINEL = "BH-GODOT-OK"
DEFAULT_PROJECT_NAME = "BlackholeGodotFixture"
DEFAULT_SCENE_PATH = "scenes/beacon.tscn"
DEFAULT_ROOT_TYPE = "Node2D"
DEFAULT_ROOT_NAME = "Root"
DEFAULT_NODE_TYPE = "Label"
DEFAULT_NODE_NAME = "Beacon"
DEFAULT_MAIN_SCENE = "res://scenes/beacon.tscn"

GODOT_ACTUATION_DONE_WHEN = (
    f"capability_exists:{GODOT_ACTUATION_ID};"
    f"capability_proved:{GODOT_ACTUATION_ID};"
    "no_skill_route"
)
GODOT_ACTUATION_GOAL = (
    "Repair Godot project-gated scene actuation: hosted game-engine tools remain "
    "unsupported so a scene tree cannot be mutated and a sealed play-check cannot "
    "be produced. A missing project.godot stays forbidden; fail-closed routing "
    "never opts the engine provider in."
)

_NODE_HEADER_RE = re.compile(
    r'\[node name="([^"]+)" type="([^"]+)"(?: parent="([^"]*)")?\]'
)
_PROP_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_/]*)\s*=\s*(.+)$")


class GodotActuationError(RuntimeError):
    """Raised when the Godot session or project fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _godot_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(raw: str) -> str:
    text = str(raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        inner = text[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return text


@dataclass
class SceneNode:
    name: str
    type: str
    parent: str = ""
    properties: dict[str, str] = field(default_factory=dict)

    def path(self) -> str:
        if not self.parent or self.parent in {".", "root", "Root"}:
            return self.name
        return f"{self.parent}/{self.name}"


@dataclass
class Scene:
    path: str
    root_type: str = DEFAULT_ROOT_TYPE
    nodes: list[SceneNode] = field(default_factory=list)

    def root(self) -> SceneNode | None:
        return self.nodes[0] if self.nodes else None

    def find(self, node_path: str) -> SceneNode | None:
        wanted = str(node_path or "").strip().lstrip("/")
        if wanted.lower() in {"", "root", ".", DEFAULT_ROOT_NAME.lower()}:
            return self.root()
        for node in self.nodes:
            if node.path() == wanted or node.name == wanted:
                return node
            if node.path().lower() == wanted.lower():
                return node
        return None

    def to_tscn(self) -> str:
        lines = ["[gd_scene load_steps=1 format=3]", ""]
        for index, node in enumerate(self.nodes):
            if index == 0:
                lines.append(f'[node name="{node.name}" type="{node.type}"]')
            else:
                parent = node.parent or "."
                lines.append(
                    f'[node name="{node.name}" type="{node.type}" parent="{parent}"]'
                )
            for key, value in node.properties.items():
                lines.append(f"{key} = {value}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def from_tscn(cls, path: str, text: str) -> Scene:
        scene = cls(path=path)
        current: SceneNode | None = None
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            header = _NODE_HEADER_RE.match(line)
            if header:
                if current is not None:
                    scene.nodes.append(current)
                name, node_type, parent = header.group(1), header.group(2), header.group(3)
                current = SceneNode(
                    name=name,
                    type=node_type,
                    parent="" if not scene.nodes else (parent or "."),
                )
                if not scene.nodes:
                    scene.root_type = node_type
                continue
            if current is None:
                continue
            prop = _PROP_RE.match(line)
            if prop:
                current.properties[prop.group(1)] = prop.group(2).strip()
        if current is not None:
            scene.nodes.append(current)
        return scene


def render_project_godot(*, name: str = DEFAULT_PROJECT_NAME, main_scene: str = DEFAULT_MAIN_SCENE) -> str:
    return (
        "; Engine configuration file.\n"
        "config_version=5\n"
        "\n"
        "[application]\n"
        f'config/name="{name}"\n'
        f'run/main_scene="{main_scene}"\n'
        'config/features=PackedStringArray("4.4")\n'
    )


class GodotProjectSession:
    """Project-gated in-process Godot 4 session: scene, node, save, play."""

    def __init__(self, *, project_open: bool = True, project_dir: Path | None = None) -> None:
        self.project_open = bool(project_open)
        self.project_dir = Path(project_dir) if project_dir else Path(
            tempfile.mkdtemp(prefix="godot-fixture-")
        )
        self.project_name = DEFAULT_PROJECT_NAME
        self.scenes: dict[str, Scene] = {}
        self.saved_paths: set[str] = set()
        self.running = False
        self.debug_lines: list[str] = []
        self.history: list[dict[str, Any]] = []
        if self.project_open:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            (self.project_dir / "project.godot").write_text(
                render_project_godot(),
                encoding="utf-8",
            )

    def _forbidden(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 403,
            "error": reason,
            "projects": [],
            "scene_path": "",
            "sentinel": "",
            "debug_output": "",
        }

    def _require_project(self) -> dict[str, Any] | None:
        if not self.project_open or not (self.project_dir / "project.godot").is_file():
            return self._forbidden("project_gated")
        return None

    def list_projects(self, directory: str = "") -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        return {
            "ok": True,
            "status": 200,
            "projects": [
                {
                    "name": self.project_name,
                    "path": str(self.project_dir),
                    "projectGodot": str(self.project_dir / "project.godot"),
                }
            ],
            "directory": str(directory or self.project_dir),
        }

    def get_project_info(self) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        return {
            "ok": True,
            "status": 200,
            "name": self.project_name,
            "path": str(self.project_dir),
            "mainScene": DEFAULT_MAIN_SCENE,
            "sceneCount": len(self.scenes),
        }

    def create_scene(self, scene_path: str, *, root_node_type: str = DEFAULT_ROOT_TYPE) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        rel = str(scene_path or DEFAULT_SCENE_PATH).replace("\\", "/").lstrip("/")
        if rel in self.scenes:
            return {"ok": False, "status": 409, "error": "scene_exists", "scene_path": rel}
        root = SceneNode(name=DEFAULT_ROOT_NAME, type=str(root_node_type or DEFAULT_ROOT_TYPE))
        scene = Scene(path=rel, root_type=root.type, nodes=[root])
        self.scenes[rel] = scene
        return {
            "ok": True,
            "status": 200,
            "scene_path": rel,
            "root_node_type": root.type,
            "node_count": len(scene.nodes),
        }

    def add_node(
        self,
        *,
        scene_path: str,
        node_type: str,
        node_name: str,
        parent_node_path: str = ".",
        properties: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        rel = str(scene_path or DEFAULT_SCENE_PATH).replace("\\", "/").lstrip("/")
        scene = self.scenes.get(rel)
        if scene is None:
            return self._forbidden("scene_gated")
        parent = scene.find(parent_node_path)
        if parent is None:
            return {"ok": False, "status": 404, "error": "missing_parent", "scene_path": rel}
        node = SceneNode(
            name=str(node_name or DEFAULT_NODE_NAME),
            type=str(node_type or DEFAULT_NODE_TYPE),
            parent="." if parent is scene.root() else parent.path(),
            properties={
                str(key): _godot_literal(value) for key, value in dict(properties or {}).items()
            },
        )
        scene.nodes.append(node)
        sentinel = SENTINEL if SENTINEL in " ".join(node.properties.values()) else ""
        return {
            "ok": True,
            "status": 200,
            "scene_path": rel,
            "node_path": node.path(),
            "node_type": node.type,
            "node_count": len(scene.nodes),
            "sentinel": sentinel,
        }

    def save_scene(self, scene_path: str) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        rel = str(scene_path or DEFAULT_SCENE_PATH).replace("\\", "/").lstrip("/")
        scene = self.scenes.get(rel)
        if scene is None:
            return self._forbidden("scene_gated")
        dest = self.project_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(scene.to_tscn(), encoding="utf-8")
        self.saved_paths.add(rel)
        return {
            "ok": True,
            "status": 200,
            "scene_path": rel,
            "saved_path": str(dest),
            "node_count": len(scene.nodes),
        }

    def run_project(self, scene_path: str = "") -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        rel = str(scene_path or DEFAULT_SCENE_PATH).replace("\\", "/").lstrip("/")
        scene = self.scenes.get(rel)
        if scene is None:
            return self._forbidden("scene_gated")
        if rel not in self.saved_paths:
            return self._forbidden("scene_gated")
        lines = [f"Godot Engine 4.4 - {self.project_name}"]
        sentinel = ""
        for node in scene.nodes:
            if node.type == "Label" and "text" in node.properties:
                text = _unquote(node.properties["text"])
                lines.append(f"{node.path()}: {text}")
                if text == SENTINEL:
                    sentinel = SENTINEL
            for value in node.properties.values():
                if SENTINEL in value:
                    sentinel = SENTINEL
        if sentinel:
            lines.append(sentinel)
        self.running = True
        self.debug_lines = lines
        return {
            "ok": True,
            "status": 200,
            "running": True,
            "scene_path": rel,
            "debug_output": "\n".join(lines),
            "sentinel": sentinel,
        }

    def get_debug_output(self) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        output = "\n".join(self.debug_lines)
        return {
            "ok": True,
            "status": 200,
            "running": self.running,
            "debug_output": output,
            "sentinel": SENTINEL if SENTINEL in output else "",
        }

    def stop_project(self) -> dict[str, Any]:
        blocked = self._require_project()
        if blocked:
            return blocked
        self.running = False
        return {
            "ok": True,
            "status": 200,
            "running": False,
            "debug_output": "\n".join(self.debug_lines),
            "sentinel": SENTINEL if SENTINEL in "\n".join(self.debug_lines) else "",
        }


def call_godot_tool(session: GodotProjectSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one godot tool call against an open project session."""

    action = str(arguments.get("action") or "").strip()
    if action == "list_projects":
        result = session.list_projects(str(arguments.get("directory") or ""))
    elif action == "get_project_info":
        result = session.get_project_info()
    elif action == "create_scene":
        result = session.create_scene(
            str(arguments.get("scenePath") or arguments.get("scene_path") or DEFAULT_SCENE_PATH),
            root_node_type=str(arguments.get("rootNodeType") or arguments.get("root_node_type") or DEFAULT_ROOT_TYPE),
        )
    elif action == "add_node":
        raw_props = arguments.get("properties") or {}
        if not isinstance(raw_props, Mapping):
            raw_props = {}
        result = session.add_node(
            scene_path=str(arguments.get("scenePath") or arguments.get("scene_path") or DEFAULT_SCENE_PATH),
            node_type=str(arguments.get("nodeType") or arguments.get("node_type") or DEFAULT_NODE_TYPE),
            node_name=str(arguments.get("nodeName") or arguments.get("node_name") or DEFAULT_NODE_NAME),
            parent_node_path=str(arguments.get("parentNodePath") or arguments.get("parent_node_path") or "."),
            properties=dict(raw_props),
        )
    elif action == "save_scene":
        result = session.save_scene(
            str(arguments.get("scenePath") or arguments.get("scene_path") or DEFAULT_SCENE_PATH)
        )
    elif action == "run_project":
        result = session.run_project(
            str(arguments.get("scene") or arguments.get("scenePath") or arguments.get("scene_path") or "")
        )
    elif action == "get_debug_output":
        result = session.get_debug_output()
    elif action == "stop_project":
        result = session.stop_project()
    else:
        raise GodotActuationError(f"unsupported godot action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def run_godot_workflow(
    *,
    project_open: bool = True,
    output_dir: Path | None = None,
    skip_scene: bool = False,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the project-gated scene-mutate-play workflow and seal a trace."""

    descriptor = godot_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GODOT_TOOL_PROVIDER),
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
        raise GodotActuationError(f"godot tool did not route executable: {decision.reasons}")

    session = GodotProjectSession(project_open=project_open, project_dir=project_dir)
    calls: list[dict[str, Any]] = [
        {"action": "list_projects", "directory": str(session.project_dir)},
        {"action": "get_project_info"},
    ]
    if not skip_scene:
        calls.append(
            {
                "action": "create_scene",
                "scenePath": DEFAULT_SCENE_PATH,
                "rootNodeType": DEFAULT_ROOT_TYPE,
            }
        )
    calls.extend(
        [
            {
                "action": "add_node",
                "scenePath": DEFAULT_SCENE_PATH,
                "parentNodePath": ".",
                "nodeType": DEFAULT_NODE_TYPE,
                "nodeName": DEFAULT_NODE_NAME,
                "properties": {"text": SENTINEL},
            },
            {"action": "save_scene", "scenePath": DEFAULT_SCENE_PATH},
            {"action": "run_project", "scene": DEFAULT_SCENE_PATH},
            {"action": "get_debug_output"},
            {"action": "stop_project"},
        ]
    )
    results: list[dict[str, Any]] = []
    for arguments in calls:
        try:
            results.append(call_godot_tool(session, arguments))
        except GodotActuationError as error:
            results.append({"action": arguments["action"], "error": str(error)})
            break
        if int(results[-1].get("status") or 0) >= 400:
            break

    final = results[-1] if results else {}
    debug = ""
    for item in reversed(results):
        if item.get("debug_output"):
            debug = str(item.get("debug_output") or "")
            break
    sentinel = SENTINEL if SENTINEL in debug or str(final.get("sentinel") or "") == SENTINEL else ""
    saved_scene = DEFAULT_SCENE_PATH in session.saved_paths
    scene_exists = DEFAULT_SCENE_PATH in session.scenes
    tscn_text = ""
    saved_path = session.project_dir / DEFAULT_SCENE_PATH
    if saved_path.is_file():
        tscn_text = saved_path.read_text(encoding="utf-8")
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "godot_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "project_open": project_open,
        "skip_scene": skip_scene,
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "sentinel": sentinel or str(final.get("sentinel") or ""),
        "debug_output": debug,
        "scene_saved": saved_scene,
        "scene_exists": scene_exists,
        "tscn": tscn_text,
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="godot-live-"))
    out.mkdir(parents=True, exist_ok=True)
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    sealed = bool(
        decision.executable
        and project_open
        and not skip_scene
        and saved_scene
        and scene_exists
        and SENTINEL in (sentinel or debug)
        and 'text = "BH-GODOT-OK"' in tscn_text
        and "[gd_scene" in tscn_text
    )
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "sentinel": sentinel or str(final.get("sentinel") or ""),
        "debug_output": debug,
        "final_status": int(final.get("status") or 0),
        "project_open": project_open,
        "scene_saved": saved_scene,
        "scene_exists": scene_exists,
        "error": str(final.get("error") or ""),
        "tscn": tscn_text,
        "project_dir": str(session.project_dir),
    }


def verify_godot_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed Godot trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    tscn = str(trace.get("tscn") or "")
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "debug_recorded": SENTINEL in str(trace.get("debug_output") or ""),
        "scene_saved": trace.get("scene_saved") is True,
        "tscn_is_godot4": "[gd_scene" in tscn and 'text = "BH-GODOT-OK"' in tscn,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def godot_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.godot_actuation import "
        "builtin_godot_actuation_proof; r=builtin_godot_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='godot_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_godot_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=GODOT_ACTUATION_ID,
        name="First-class Godot scene actuation",
        description=(
            "Missions that require a Godot tool can opt the godot provider in, "
            "open a project.godot, mutate a scene tree, and seal a digest-chained "
            "play-check. Default routing stays fail-closed; a missing project keeps "
            "the project-open hole falsifiable, and node mutation stays scene-gated."
        ),
        kind="python",
        entry="blackhole_agent.godot_actuation:builtin_godot_actuation_proof",
        proof_command=godot_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.gmail-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/godot_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required Godot tool is executable after explicit provider opt-in: "
            "Unbound opens a project.godot, creates a Godot 4 scene, adds a Label "
            "beacon, seals a tamper-evident play-check, and binds this family as "
            "the next diversity-catalog successor once Gmail actuation is proved."
        ),
        tags=("godot", "scene", "actuation", "engine", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T030648Z-bc1d0e98",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_godot_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in Godot actuation seals a project-gated play-check."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.browser_actuation import BROWSER_ACTUATION_GOAL, BROWSER_ACTUATION_ID

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = GODOT_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(GODOT_ACTUATION_GOAL) == (
        GODOT_ACTUATION_ID,
    )
    checks["gmail_goal_is_not_godot"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) != (
        GODOT_ACTUATION_ID,
    )
    checks["browser_goal_is_not_godot"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) != (
        GODOT_ACTUATION_ID,
    )
    checks["gmail_marker_stays_gmail"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["browser_marker_stays_browser"] = leftover_marker_ids(BROWSER_ACTUATION_GOAL) == (
        BROWSER_ACTUATION_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_godot"] = (
        len(catalog) > 11
        and catalog[11]["id"] == GODOT_ACTUATION_ID
        and catalog[10]["id"] == GMAIL_ACTUATION_ID
    )

    mcp_engine = ToolDescriptor(name="remote_godot", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_engine)
    checks["naive_mcp_godot_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = godot_tool_descriptor()
    default_engine = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GODOT_TOOL_PROVIDER),
    )
    checks["default_godot_provider_is_unsupported"] = (
        default_engine.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{GODOT_TOOL_PROVIDER}" in default_engine.reasons
    )
    checks["opted_in_godot_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_engine],
        required_tool_names=("local_memory", "godot"),
    )
    checks["naive_preflight_missing_godot"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["godot"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "godot"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, GODOT_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "godot" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="godot-actuation-") as tmp:
        root = Path(tmp)
        naive = run_godot_workflow(project_open=False, output_dir=root / "naive")
        unscene = run_godot_workflow(skip_scene=True, output_dir=root / "unscene")
        live = run_godot_workflow(output_dir=root / "live")
        verify = verify_godot_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_godot_trace(clone)
        parsed = Scene.from_tscn(DEFAULT_SCENE_PATH, str(live.get("tscn") or ""))
        beacon = parsed.find(DEFAULT_NODE_NAME)
        checks["naive_without_project_is_forbidden"] = (
            naive["ok"] is False
            and naive["sentinel"] == ""
            and naive["final_status"] == 403
            and naive["error"] == "project_gated"
        )
        checks["unscene_node_is_forbidden"] = (
            unscene["ok"] is False
            and unscene["final_status"] == 403
            and unscene["error"] == "scene_gated"
            and unscene["scene_exists"] is False
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_writes_godot4_tscn"] = (
            "[gd_scene" in str(live.get("tscn") or "")
            and 'text = "BH-GODOT-OK"' in str(live.get("tscn") or "")
            and beacon is not None
            and _unquote(beacon.properties.get("text") or "") == SENTINEL
        )
        checks["workflow_saves_and_plays"] = live["scene_saved"] is True and live["ok"] is True
        checks["project_and_scene_are_required"] = (
            naive["ok"] is False and unscene["ok"] is False and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="godot-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != GODOT_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_godot"] = (
        live_goal == GODOT_ACTUATION_GOAL
        and GODOT_ACTUATION_ID in live_done
        and live_source == "genesis_bind_godot"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_godot_actuation_capability()
    return {
        "ok": ok,
        "action": "godot_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": GODOT_ACTUATION_GOAL,
        "done_when": GODOT_ACTUATION_DONE_WHEN,
    }
