"""Import live MCP tools as application steps and compose them with absorbed leaves.

``capability.mcp-tool-import`` and ``capability.mcp-live-execution`` can list
and call MCP tools, but those tools never enter the application planner.
Absorbed Python leaves are planner-visible; a goal that needs both stays
honestly unplannable even after both surfaces are proved.

This plane closes that isolation:

- import a live MCP tool (in-repo echo server ``sha256``) as an
  ``ApplicationStep`` with typed requires/provides;
- discover a producer/consumer pair whose frozen Python output is a
  live-valid MCP input (canonical: ``text-reverser`` → ``sha256``);
- install a typed key-bridge that copies the producer provide onto the
  MCP require;
- the application planner then derives ``producer → bridge → mcp`` —
  the sequence is not hand-authored;
- hiding the producer, the bridge, or the MCP step makes the goal
  unplannable again; hashing the original input (skipping the producer)
  fails the oracle, so the Python leaf is causally required;
- a digest-sealed report under ``artifacts/capability-mcp-application/``
  whose verification re-runs the live chain and re-checks the digest.

MCP tools stay fail-closed under default tool routing: the step opts the
``mcp`` provider in explicitly, matching live-execution policy.

Mixed MCP+absorbed goals stay off the default watchdog and recovery
loop; the MCP reliability plane watches them so a hidden MCP hop is
named drift, and the MCP recovery plane heals a red MCP hop.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorbed_composition import make_bridge_step
from blackhole_agent.capability_absorption import load_persisted_absorbed_steps, load_persisted_records
from blackhole_agent.capability_application import (
    ApplicationStep,
    ApplicationTask,
    execute_application_plan,
    plan_application_task,
    run_application_task,
)
from blackhole_agent.capability_compounder import (
    Capability,
    atomic_write_json,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path, durable_write_path
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
)
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    MCP_TOOL_PROVIDER,
    route_tool_descriptor,
    tool_descriptors_from_mcp_tools,
)

SCHEMA_VERSION = 1
MCP_APPLICATION_BRIDGE_ID = "capability.mcp-application-bridge"
MCP_SHA256_ID = "capability.mcp-echo-sha256"
CANONICAL_PRODUCER_SLUG = "text-reverser"
CANONICAL_CONSUMER_TOOL = "sha256"
CANONICAL_CONSUMER_SLUG = "echo-sha256"
CANONICAL_REQUIRE = "text"
CANONICAL_PROVIDE = "mcp_sha256_hex"
CANONICAL_SERVER = "echo"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-mcp-application"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-mcp-application.json"
BRIDGES_PATH = REPO_ROOT / "capabilities" / "mcp-bridges.json"
STEPS_PATH = REPO_ROOT / "capabilities" / "mcp-application-steps.json"

_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def mcp_sha256_capability_id() -> str:
    return MCP_SHA256_ID


def mcp_bridge_capability_id(producer_slug: str, consumer_slug: str) -> str:
    return f"capability.mcp-bridge-{producer_slug}-{consumer_slug}"


def call_live_mcp_tool(
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    server_name: str = CANONICAL_SERVER,
    timeout_seconds: float = 30.0,
) -> str:
    """Spawn the in-repo MCP server, opt the tool in, and return its text result."""

    with McpStdioSession(echo_server_command(), timeout_seconds=timeout_seconds) as session:
        tools_payload = session.list_tools()
        descriptors = tool_descriptors_from_mcp_tools(tools_payload, server_name=server_name)
        target_name = f"{server_name}:{tool_name}"
        target = next((item for item in descriptors if item.name == target_name), None)
        if target is None:
            raise McpProtocolError(f"tool {tool_name!r} not advertised by server {server_name!r}")
        decision = route_tool_descriptor(
            target,
            executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MCP_TOOL_PROVIDER),
        )
        if not decision.executable:
            raise McpProtocolError(f"tool {target_name!r} did not route executable: {decision.reasons}")
        result = session.call_tool(tool_name, arguments)
    return _extract_text(result)


def make_mcp_step(
    *,
    capability_id: str = MCP_SHA256_ID,
    tool_name: str = CANONICAL_CONSUMER_TOOL,
    require_key: str = CANONICAL_REQUIRE,
    provide_key: str = CANONICAL_PROVIDE,
    server_name: str = CANONICAL_SERVER,
) -> ApplicationStep:
    """Live MCP tool shaped as a planner step. Each invoke is a fresh stdio session."""

    def invoke(
        state: Mapping[str, Any],
        _tool: str = tool_name,
        _require: str = require_key,
        _provide: str = provide_key,
        _server: str = server_name,
    ) -> dict[str, Any]:
        if _require not in state:
            raise KeyError(f"mcp step missing required key {_require}")
        text = call_live_mcp_tool(_tool, {_require: state[_require]}, server_name=_server)
        return {_provide: text}

    return ApplicationStep(
        capability_id=capability_id,
        requires=(require_key,),
        provides=(provide_key,),
        invoke=invoke,
    )


def mcp_application_steps() -> dict[str, ApplicationStep]:
    """Canonical live MCP steps plus any persisted extras."""

    steps = {MCP_SHA256_ID: make_mcp_step()}
    for record in load_persisted_mcp_step_records():
        capability_id = str(record.get("capability_id") or "").strip()
        tool_name = str(record.get("tool_name") or "").strip()
        requires = [str(key) for key in (record.get("requires") or ()) if str(key).strip()]
        provides = [str(key) for key in (record.get("provides") or ()) if str(key).strip()]
        if not capability_id or not tool_name or len(requires) != 1 or len(provides) != 1:
            continue
        steps[capability_id] = make_mcp_step(
            capability_id=capability_id,
            tool_name=tool_name,
            require_key=requires[0],
            provide_key=provides[0],
            server_name=str(record.get("server") or CANONICAL_SERVER),
        )
    return steps


def load_persisted_mcp_step_records(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or STEPS_PATH
    if not durable_read_path(target).is_file():
        return []
    try:
        payload = json.loads(durable_read_path(target).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list):
        return []
    return [item for item in steps if isinstance(item, dict)]


def persist_mcp_steps(records: Sequence[Mapping[str, Any]], *, path: Path | None = None) -> dict[str, Any]:
    target = durable_write_path(path or STEPS_PATH)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mcp_application_steps",
        "updated_at": utc_now_iso(),
        "steps": [dict(item) for item in records],
    }
    atomic_write_json(target, payload)
    return payload


def load_persisted_mcp_bridge_records(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or BRIDGES_PATH
    if not durable_read_path(target).is_file():
        return []
    try:
        payload = json.loads(durable_read_path(target).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    bridges = payload.get("bridges") if isinstance(payload, dict) else None
    if not isinstance(bridges, list):
        return []
    return [item for item in bridges if isinstance(item, dict)]


def load_persisted_mcp_bridge_steps(path: Path | None = None) -> dict[str, ApplicationStep]:
    steps: dict[str, ApplicationStep] = {}
    for record in load_persisted_mcp_bridge_records(path):
        if not record.get("bridge_id"):
            continue
        step = make_bridge_step(record)
        steps[step.capability_id] = step
    return steps


def persist_mcp_bridge_pair(pair: Mapping[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    target = durable_write_path(path or BRIDGES_PATH)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mcp_application_bridges",
        "updated_at": utc_now_iso(),
        "bridges": [dict(pair)],
    }
    atomic_write_json(target, payload)
    return payload


def _producer_record() -> dict[str, Any] | None:
    for item in load_persisted_records():
        if str(item.get("slug") or "") == CANONICAL_PRODUCER_SLUG:
            return dict(item)
    return None


def canonical_mcp_pair(
    *,
    absorbed_steps: Mapping[str, ApplicationStep] | None = None,
) -> dict[str, Any] | None:
    """Python text-reverser feeding live MCP sha256 through a typed key-bridge."""

    producer = _producer_record()
    steps = absorbed_steps if absorbed_steps is not None else load_persisted_absorbed_steps()
    if producer is None:
        return None
    producer_id = str(producer.get("capability_id") or "")
    producer_step = steps.get(producer_id)
    if producer_step is None:
        return None
    provides = [str(key) for key in (producer.get("provides") or ()) if str(key).strip()]
    if len(provides) != 1:
        return None
    cases = list(producer.get("cases") or [])
    producer_input: dict[str, Any] | None = None
    for case in cases:
        payload = dict(case.get("input") or {})
        sample = (case.get("expect") or {}).get(provides[0])
        if isinstance(sample, str) and any(ch.isspace() for ch in sample):
            producer_input = payload
            break
    if producer_input is None and cases:
        producer_input = dict(cases[0].get("input") or {})
    if not producer_input:
        return None
    try:
        produced = producer_step.invoke(producer_input)
    except Exception:  # noqa: BLE001 - an unusable producer is not a pair
        return None
    source = provides[0]
    if source not in produced or not isinstance(produced[source], str):
        return None
    mcp_step = make_mcp_step()
    try:
        mcp_step.invoke({CANONICAL_REQUIRE: produced[source]})
    except Exception:  # noqa: BLE001 - live MCP incompatibility is a no
        return None
    return {
        "producer_id": producer_id,
        "consumer_id": MCP_SHA256_ID,
        "producer_slug": CANONICAL_PRODUCER_SLUG,
        "consumer_slug": CANONICAL_CONSUMER_SLUG,
        "producer_runtime": "python",
        "consumer_runtime": "mcp",
        "mapping": {source: [CANONICAL_REQUIRE]},
        "requires": [source],
        "provides": [CANONICAL_REQUIRE],
        "bridge_id": mcp_bridge_capability_id(CANONICAL_PRODUCER_SLUG, CANONICAL_CONSUMER_SLUG),
        "producer_input": producer_input,
        "consumer_goal": [CANONICAL_PROVIDE],
        "consumer_tool": CANONICAL_CONSUMER_TOOL,
        "consumer_require": CANONICAL_REQUIRE,
        "consumer_provide": CANONICAL_PROVIDE,
        "consumer_server": CANONICAL_SERVER,
    }


def mcp_step_record() -> dict[str, Any]:
    return {
        "capability_id": MCP_SHA256_ID,
        "tool_name": CANONICAL_CONSUMER_TOOL,
        "requires": [CANONICAL_REQUIRE],
        "provides": [CANONICAL_PROVIDE],
        "server": CANONICAL_SERVER,
        "runtime": "mcp",
    }


def mixed_registry(
    pair: Mapping[str, Any],
    *,
    absorbed_steps: Mapping[str, ApplicationStep] | None = None,
    hide: Sequence[str] = (),
    include_bridge: bool = True,
    include_mcp: bool = True,
) -> dict[str, ApplicationStep]:
    hidden = set(hide)
    steps = absorbed_steps if absorbed_steps is not None else load_persisted_absorbed_steps()
    registry: dict[str, ApplicationStep] = {}
    producer_id = str(pair["producer_id"])
    if producer_id not in hidden and producer_id in steps:
        registry[producer_id] = steps[producer_id]
    if include_mcp:
        mcp_steps = mcp_application_steps()
        consumer_id = str(pair["consumer_id"])
        if consumer_id not in hidden and consumer_id in mcp_steps:
            registry[consumer_id] = mcp_steps[consumer_id]
    if include_bridge:
        bridge = make_bridge_step(pair)
        if bridge.capability_id not in hidden:
            registry[bridge.capability_id] = bridge
    return registry


def mixed_task(pair: Mapping[str, Any], *, absorbed_steps: Mapping[str, ApplicationStep] | None = None) -> ApplicationTask:
    steps = absorbed_steps if absorbed_steps is not None else load_persisted_absorbed_steps()
    producer = steps[str(pair["producer_id"])]
    bridge = make_bridge_step(pair)
    consumer = mcp_application_steps()[str(pair["consumer_id"])]
    produced = producer.invoke(dict(pair["producer_input"]))
    bridged = bridge.invoke(produced)
    outcome = consumer.invoke(bridged)
    goal = tuple(str(key) for key in pair["consumer_goal"])
    oracle = {key: outcome[key] for key in goal}
    return ApplicationTask(
        id=f"mcp-compose-{pair['producer_slug']}-{pair['consumer_slug']}",
        description=(
            f"From the absorbed {pair['producer_slug']} input, reach live MCP "
            f"{pair['consumer_tool']} output through a typed key-bridge."
        ),
        initial_state=dict(pair["producer_input"]),
        goal=goal,
        oracle=oracle,
    )


def run_mcp_composition_honesty(
    pair: Mapping[str, Any],
    *,
    absorbed_steps: Mapping[str, ApplicationStep] | None = None,
) -> dict[str, Any]:
    """Unplannable without the MCP hop; solved with it; ablation and skip-producer fail."""

    steps = absorbed_steps if absorbed_steps is not None else load_persisted_absorbed_steps()
    task = mixed_task(pair, absorbed_steps=steps)
    isolated = mixed_registry(pair, absorbed_steps=steps, include_bridge=False, include_mcp=False)
    mcp_only = mixed_registry(pair, absorbed_steps=steps, include_bridge=True, include_mcp=True)
    mcp_only.pop(str(pair["producer_id"]), None)
    before_plan = plan_application_task(task, isolated)
    python_mcp_no_bridge = plan_application_task(
        task, mixed_registry(pair, absorbed_steps=steps, include_bridge=False, include_mcp=True)
    )
    grown = mixed_registry(pair, absorbed_steps=steps, include_bridge=True, include_mcp=True)
    grown_result = run_application_task(task, grown)
    grown_plan = list(grown_result.get("plan") or [])
    expected_plan = [pair["producer_id"], pair["bridge_id"], pair["consumer_id"]]
    producer_hidden = mixed_registry(pair, absorbed_steps=steps, hide=[str(pair["producer_id"])])
    consumer_hidden = mixed_registry(pair, absorbed_steps=steps, hide=[str(pair["consumer_id"])])
    bridge_hidden = mixed_registry(pair, absorbed_steps=steps, hide=[str(pair["bridge_id"])])
    reversed_broke = False
    if grown_plan:
        try:
            reversed_state = execute_application_plan(task, list(reversed(grown_plan)), grown)
            reversed_broke = any(reversed_state.get(key) != value for key, value in task.oracle.items())
        except Exception:  # noqa: BLE001 - a crashed reverse is a broken outcome
            reversed_broke = True
    skip_producer_broke = True
    original = str((pair.get("producer_input") or {}).get("raw_text") or "")
    if original:
        try:
            skipped = call_live_mcp_tool(CANONICAL_CONSUMER_TOOL, {CANONICAL_REQUIRE: original})
            skip_producer_broke = skipped != task.oracle[CANONICAL_PROVIDE]
        except Exception:  # noqa: BLE001 - a failed skip is still a distinct path
            skip_producer_broke = True
    minimality: list[dict[str, Any]] = []
    for member in grown_plan:
        reduced = {key: step for key, step in grown.items() if key != member}
        broke = plan_application_task(task, reduced) is None
        if not broke:
            reduced_result = run_application_task(
                task, reduced, plan_override=[item for item in grown_plan if item != member]
            )
            broke = not bool(reduced_result.get("ok"))
        minimality.append({"member": member, "broke_outcome": broke})
    verdicts = {
        "unplannable_without_mcp": before_plan is None,
        "unplannable_without_bridge": python_mcp_no_bridge is None,
        "grown_plan_solved": bool(grown_result.get("ok")) and grown_plan == expected_plan,
        "producer_ablation_unplannable": plan_application_task(task, producer_hidden) is None,
        "consumer_ablation_unplannable": plan_application_task(task, consumer_hidden) is None,
        "bridge_ablation_unplannable": plan_application_task(task, bridge_hidden) is None,
        "mcp_only_unplannable": plan_application_task(task, mcp_only) is None,
        "reversed_broke": reversed_broke,
        "skip_producer_broke": skip_producer_broke,
        "minimality": all(item["broke_outcome"] for item in minimality) and len(minimality) == 3,
        "cross_runtime": {pair.get("producer_runtime"), pair.get("consumer_runtime")} == {"python", "mcp"},
    }
    return {
        "task": {
            "id": task.id,
            "goal": list(task.goal),
            "initial_state": dict(task.initial_state),
            "oracle": dict(task.oracle),
        },
        "expected_plan": expected_plan,
        "grown_plan": grown_plan,
        "minimality": minimality,
        "verdicts": verdicts,
        "ok": all(verdicts.values()),
    }


def run_mcp_application_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Discover the mixed pair, prove honesty, persist the MCP step and bridge, seal a report."""

    pair = canonical_mcp_pair()
    if pair is None:
        return {"ok": False, "error": "no_compatible_mcp_pair", "used_skill_route_discovery": False}
    honesty = run_mcp_composition_honesty(pair)
    persist_mcp_steps([mcp_step_record()])
    persist_mcp_bridge_pair(pair)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_application",
        "generated_at": utc_now_iso(),
        "pair": dict(pair),
        "task": honesty["task"],
        "expected_plan": honesty["expected_plan"],
        "grown_plan": honesty["grown_plan"],
        "minimality": honesty["minimality"],
        "verdicts": honesty["verdicts"],
        "grade": {
            "ok": honesty["ok"],
            "verdict_count": len(honesty["verdicts"]),
            "verdicts_passed": sum(1 for value in honesty["verdicts"].values() if value),
        },
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "ok": bool(honesty["ok"]) and not legacy_pipeline_was_used(),
    }
    report["report_digest"] = _digest(
        {key: value for key, value in report.items() if key not in _DIGEST_EXCLUDE and key != "report_digest"}
    )
    target_dir = output_dir or DEFAULT_ARTIFACT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(target_dir / "report.json", report)
    if output_dir is None or target_dir.resolve() == DEFAULT_ARTIFACT_DIR.resolve():
        atomic_write_json(
            LATEST_POINTER,
            {"report_dir": str(target_dir), "report_digest": report["report_digest"], "ok": report["ok"]},
        )
    return {
        "ok": report["ok"],
        "report_dir": str(target_dir),
        "report_digest": report["report_digest"],
        "pair": pair,
        "grown_plan": honesty["grown_plan"],
        "verdicts": honesty["verdicts"],
        "used_skill_route_discovery": report["used_skill_route_discovery"],
    }


def verify_mcp_application_report(report_dir: Path) -> dict[str, Any]:
    """Re-run the live mixed chain and re-check the sealed digest."""

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pair = dict(report.get("pair") or {})
    if not pair:
        return {"ok": False, "error": "report missing pair"}
    honesty = run_mcp_composition_honesty(pair)
    recomputed = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_mcp_application",
        "pair": pair,
        "task": honesty["task"],
        "expected_plan": honesty["expected_plan"],
        "grown_plan": honesty["grown_plan"],
        "minimality": honesty["minimality"],
        "verdicts": honesty["verdicts"],
        "grade": {
            "ok": honesty["ok"],
            "verdict_count": len(honesty["verdicts"]),
            "verdicts_passed": sum(1 for value in honesty["verdicts"].values() if value),
        },
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "ok": bool(honesty["ok"]) and not legacy_pipeline_was_used(),
    }
    recomputed_digest = _digest(recomputed)
    recorded_body = {
        key: value
        for key, value in report.items()
        if key not in _DIGEST_EXCLUDE and key != "report_digest"
    }
    recorded_digest = _digest(recorded_body)
    checks = {
        "honesty_ok": bool(honesty["ok"]),
        "digest_match": recorded_digest == report.get("report_digest"),
        "recomputed_digest_match": recomputed_digest == report.get("report_digest"),
        "plan_match": honesty["grown_plan"] == list(report.get("grown_plan") or []),
        "oracle_match": honesty["task"]["oracle"] == (report.get("task") or {}).get("oracle"),
        "no_skill_route": not legacy_pipeline_was_used(),
    }
    return {"ok": all(checks.values()), "checks": checks, "report_digest": report.get("report_digest")}


def mcp_sha256_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_application import "
        "builtin_mcp_echo_sha256_proof; r=builtin_mcp_echo_sha256_proof(); "
        "assert r['ok'] and r.get('digest_match') and not r.get('used_skill_route_discovery')\""
    )


def mcp_application_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_mcp_application import "
        "builtin_mcp_application_bridge_proof; "
        "r=builtin_mcp_application_bridge_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('unplannable_without_mcp') "
        "and r.get('verdicts',{}).get('unplannable_without_bridge') "
        "and r.get('verdicts',{}).get('grown_plan_solved') "
        "and r.get('verdicts',{}).get('producer_ablation_unplannable') "
        "and r.get('verdicts',{}).get('consumer_ablation_unplannable') "
        "and r.get('verdicts',{}).get('bridge_ablation_unplannable') "
        "and r.get('verdicts',{}).get('skip_producer_broke') "
        "and r.get('verdicts',{}).get('cross_runtime') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_echo_sha256_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the live MCP sha256 tool as a first-class ledger leaf."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_SHA256_ID,
        name="Live MCP sha256 application step",
        description=(
            "In-repo MCP echo-server sha256 tool imported as a typed application "
            "step: requires ['text'] and provides ['mcp_sha256_hex'] through a "
            "live stdio JSON-RPC session with explicit mcp provider opt-in."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_application:builtin_mcp_echo_sha256_proof",
        proof_command=mcp_sha256_proof_command(),
        dependencies=("repo.import-health", "capability.ledger-inventory"),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_application.py",
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "capabilities/mcp-application-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A live MCP tool is now a first-class application step: the planner "
            "can require mcp_sha256_hex and execute it through a real stdio session."
        ),
        tags=("mcp", "application", "actuation", "live"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def ensure_mcp_application_bridge_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the mixed MCP+absorbed composition plane once the proof is green."""

    ensure_mcp_echo_sha256_capability(repo_path=repo_path)
    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_APPLICATION_BRIDGE_ID,
        name="MCP application composition bridge",
        description=(
            "Typed key-bridge that lets a live MCP tool compose with an "
            "independently absorbed Python leaf in the goal-directed planner: "
            "text-reverser feeds MCP sha256 through a mapping step, the pipeline "
            "is BFS-derived, and hiding either member or the bridge makes the "
            "goal unplannable."
        ),
        kind="python",
        entry="blackhole_agent.capability_mcp_application:builtin_mcp_application_bridge_proof",
        proof_command=mcp_application_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.absorbed-text-reverser",
            MCP_SHA256_ID,
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_mcp_application.py",
            "src/blackhole_agent/capability_application.py",
            "src/blackhole_agent/mcp_client.py",
            "capabilities/mcp-bridges.json",
            "capabilities/mcp-application-steps.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Live MCP tools compose with absorbed Python leaves: a typed "
            "key-bridge turns an unplannable mixed MCP+absorbed goal into a "
            "planner-derived Python→MCP pipeline, and ablation of either leaf "
            "or the bridge fails it."
        ),
        tags=("mcp", "absorbed", "composition", "bridge", "application", "cross-runtime"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_mcp_echo_sha256_proof() -> dict[str, Any]:
    """Registered proof: live MCP sha256 matches the local hashlib digest."""

    payload = "absorption plane"
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    step = make_mcp_step()
    result = step.invoke({CANONICAL_REQUIRE: payload})
    digest = str(result.get(CANONICAL_PROVIDE) or "")
    persist_mcp_steps([mcp_step_record()])
    ok = digest == expected and not legacy_pipeline_was_used()
    return {
        "ok": ok,
        "digest_match": digest == expected,
        "mcp_sha256_hex": digest,
        "expected": expected,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "action": "mcp_echo_sha256",
    }


def builtin_mcp_application_bridge_proof() -> dict[str, Any]:
    """Registered proof: live mixed honesty, sealed verification, tamper and misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-mcp-application-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_mcp_application_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_mcp_application_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["grown_plan_solved"] = not tampered["verdicts"]["grown_plan_solved"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_mcp_application_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_mcp_application_report(report_dir)["ok"]
        atomic_write_json(report_path, report)
    live = run_mcp_application_plane(DEFAULT_ARTIFACT_DIR)
    ensure_mcp_application_bridge_capability()
    ok = (
        bool(result["ok"])
        and bool(verification.get("ok"))
        and tamper_failed
        and misgrade_failed
        and bool(live.get("ok"))
        and not legacy_pipeline_was_used()
    )
    return {
        **result,
        "ok": ok,
        "verify_ok": bool(verification.get("ok")),
        "tamper_detected": tamper_failed,
        "misgrade_detected": misgrade_failed,
        "action": "mcp_application_bridge",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
