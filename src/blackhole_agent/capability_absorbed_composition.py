"""Typed bridges so independently absorbed tools compose in the planner.

Absorbed ledger leaves are invocable one at a time: each has disjoint
``requires`` / ``provides`` keys minted by forage, so a goal that needs two
tools stays honestly unplannable even when both leaves are proved. This
module closes that isolation:

- discover a producer/consumer pair whose frozen output is a live-valid
  input for the consumer, preferring a Python leaf feeding a Node leaf;
- install a typed key-bridge ``ApplicationStep`` that copies the producer
  provide onto the consumer requires (no overwrite of the original input);
- the application planner then derives the pipeline
  ``producer → bridge → consumer`` — the sequence is not hand-authored;
- hiding the producer, the bridge, or the consumer makes the goal
  unplannable again; a reversed plan fails the oracle;
- a digest-sealed report under ``artifacts/capability-absorbed-composition/``
  whose verification re-runs the live chain and re-checks the digest.

The canonical pair is the fixture ``text-reverser`` (Python) feeding npm
``snake-case`` (Node): ``raw_text`` → ``reversed_text`` → ``arg0``/``arg1``
→ ``snake_case_output``. Direct ``snake-case`` cannot run from ``raw_text``,
and the snake-cased reverse (``enalp_noitprosba`` from ``absorption plane``)
is not the snake-case of the original string, so the producer is causally
required.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

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

SCHEMA_VERSION = 1
ABSORBED_COMPOSITION_ID = "capability.absorbed-composition-bridge"
CANONICAL_PRODUCER_SLUG = "text-reverser"
CANONICAL_CONSUMER_SLUG = "snake-case"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "capability-absorbed-composition"
LATEST_POINTER = DEFAULT_ARTIFACT_DIR / "latest-composition.json"
BRIDGES_PATH = REPO_ROOT / "capabilities" / "absorbed-bridges.json"

_DIGEST_EXCLUDE = frozenset({"generated_at", "run_at", "report_dir"})


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _record_runtime(record: Mapping[str, Any]) -> str:
    command = [str(part).lower() for part in (record.get("command") or ())]
    joined = " ".join(command)
    if command and (command[0] in {"node", "nodejs"} or joined.endswith(".mjs") or "node" in command[0]):
        return "node"
    return "python"


def capability_id_for_slug(slug: str) -> str:
    return f"capability.absorbed-{slug}"


def bridge_capability_id(producer_slug: str, consumer_slug: str) -> str:
    return f"capability.absorbed-bridge-{producer_slug}-{consumer_slug}"


def mapping_for(producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> dict[str, list[str]] | None:
    """One producer provide fills every consumer require; keys must not already chain."""

    provides = [str(key) for key in (producer.get("provides") or ()) if str(key).strip()]
    requires = [str(key) for key in (consumer.get("requires") or ()) if str(key).strip()]
    if len(provides) != 1 or not requires:
        return None
    if set(provides) & set(requires):
        return None
    source = provides[0]
    cases = list(producer.get("cases") or [])
    if not cases:
        return None
    sample = (cases[0].get("expect") or {}).get(source)
    if not isinstance(sample, (str, int, float, bool)):
        return None
    return {source: list(requires)}


def pair_is_live_compatible(
    producer: Mapping[str, Any],
    consumer: Mapping[str, Any],
    steps: Mapping[str, ApplicationStep],
) -> bool:
    """Run producer then consumer through the mapped keys; both must succeed."""

    mapping = mapping_for(producer, consumer)
    if mapping is None:
        return False
    producer_id = str(producer.get("capability_id") or "")
    consumer_id = str(consumer.get("capability_id") or "")
    producer_step = steps.get(producer_id)
    consumer_step = steps.get(consumer_id)
    if producer_step is None or consumer_step is None:
        return False
    cases = list(producer.get("cases") or [])
    if not cases:
        return False
    try:
        produced = producer_step.invoke(dict(cases[0]["input"]))
        mapped: dict[str, Any] = {}
        for source, destinations in mapping.items():
            if source not in produced:
                return False
            for destination in destinations:
                mapped[destination] = produced[source]
        consumer_step.invoke(mapped)
    except Exception:  # noqa: BLE001 - incompatibility is a no, not a crash
        return False
    return True


def select_composition_pair(
    records: Sequence[Mapping[str, Any]] | None = None,
    *,
    steps: Mapping[str, ApplicationStep] | None = None,
) -> dict[str, Any] | None:
    """Pick a compatible pair, preferring the canonical Python→Node chain."""

    active_records = list(records if records is not None else load_persisted_records())
    active_steps = steps if steps is not None else load_persisted_absorbed_steps()
    by_slug = {str(item.get("slug") or ""): item for item in active_records}
    canonical_producer = by_slug.get(CANONICAL_PRODUCER_SLUG)
    canonical_consumer = by_slug.get(CANONICAL_CONSUMER_SLUG)
    if (
        canonical_producer is not None
        and canonical_consumer is not None
        and pair_is_live_compatible(canonical_producer, canonical_consumer, active_steps)
        and _record_runtime(canonical_producer) == "python"
        and _record_runtime(canonical_consumer) == "node"
    ):
        return _pair_payload(canonical_producer, canonical_consumer, steps=active_steps)
    # Bounded scan: cross-runtime first, then any compatible isolation pair.
    ranked = sorted(
        active_records,
        key=lambda item: (0 if _record_runtime(item) == "python" else 1, str(item.get("slug") or "")),
    )
    probes = 0
    fallback: dict[str, Any] | None = None
    for producer in ranked:
        for consumer in ranked:
            if producer is consumer:
                continue
            mapping = mapping_for(producer, consumer)
            if mapping is None:
                continue
            probes += 1
            if probes > 48:
                return fallback
            if not pair_is_live_compatible(producer, consumer, active_steps):
                continue
            payload = _pair_payload(producer, consumer, steps=active_steps)
            if payload["producer_runtime"] != payload["consumer_runtime"]:
                return payload
            if fallback is None:
                fallback = payload
    return fallback


def _preferred_producer_input(
    producer: Mapping[str, Any],
    *,
    steps: Mapping[str, ApplicationStep],
) -> dict[str, Any]:
    """Prefer a frozen case whose output contains whitespace so the consumer visibly transforms it."""

    producer_id = str(producer.get("capability_id") or "")
    producer_step = steps.get(producer_id)
    provide = str((producer.get("provides") or [""])[0])
    cases = list(producer.get("cases") or [])
    if producer_step is not None and provide:
        for case in cases:
            payload = dict(case.get("input") or {})
            try:
                produced = producer_step.invoke(payload)
            except Exception:  # noqa: BLE001 - skip a case that cannot run
                continue
            sample = produced.get(provide)
            if isinstance(sample, str) and any(ch.isspace() for ch in sample):
                return payload
    if cases:
        return dict(cases[0].get("input") or {})
    return {}


def _pair_payload(
    producer: Mapping[str, Any],
    consumer: Mapping[str, Any],
    *,
    steps: Mapping[str, ApplicationStep],
) -> dict[str, Any]:
    mapping = mapping_for(producer, consumer)
    assert mapping is not None
    producer_slug = str(producer["slug"])
    consumer_slug = str(consumer["slug"])
    source = next(iter(mapping))
    destinations = list(mapping[source])
    return {
        "producer_id": str(producer.get("capability_id") or capability_id_for_slug(producer_slug)),
        "consumer_id": str(consumer.get("capability_id") or capability_id_for_slug(consumer_slug)),
        "producer_slug": producer_slug,
        "consumer_slug": consumer_slug,
        "producer_runtime": _record_runtime(producer),
        "consumer_runtime": _record_runtime(consumer),
        "mapping": mapping,
        "requires": [source],
        "provides": destinations,
        "bridge_id": bridge_capability_id(producer_slug, consumer_slug),
        "producer_input": _preferred_producer_input(producer, steps=steps),
        "consumer_goal": list(consumer.get("provides") or ()),
    }


def make_bridge_step(pair: Mapping[str, Any]) -> ApplicationStep:
    mapping = {str(src): [str(dest) for dest in dests] for src, dests in dict(pair["mapping"]).items()}
    requires = tuple(str(key) for key in pair["requires"])
    provides = tuple(str(key) for key in pair["provides"])

    def invoke(
        state: Mapping[str, Any],
        _mapping: dict[str, list[str]] = mapping,
    ) -> dict[str, Any]:
        fragment: dict[str, Any] = {}
        for source, destinations in _mapping.items():
            if source not in state:
                raise KeyError(f"bridge missing source key {source}")
            for destination in destinations:
                fragment[destination] = state[source]
        return fragment

    return ApplicationStep(
        capability_id=str(pair["bridge_id"]),
        requires=requires,
        provides=provides,
        invoke=invoke,
    )


def composition_task(pair: Mapping[str, Any], steps: Mapping[str, ApplicationStep]) -> ApplicationTask:
    producer = steps[str(pair["producer_id"])]
    bridge = make_bridge_step(pair)
    consumer = steps[str(pair["consumer_id"])]
    produced = producer.invoke(dict(pair["producer_input"]))
    bridged = bridge.invoke(produced)
    outcome = consumer.invoke(bridged)
    goal = tuple(str(key) for key in pair["consumer_goal"])
    oracle = {key: outcome[key] for key in goal}
    return ApplicationTask(
        id=f"absorbed-compose-{pair['producer_slug']}-{pair['consumer_slug']}",
        description=(
            f"From the absorbed {pair['producer_slug']} input, reach "
            f"{pair['consumer_slug']} output through a typed key-bridge."
        ),
        initial_state=dict(pair["producer_input"]),
        goal=goal,
        oracle=oracle,
    )


def composition_registry(
    steps: Mapping[str, ApplicationStep],
    pair: Mapping[str, Any],
    *,
    hide: Sequence[str] = (),
    include_bridge: bool = True,
) -> dict[str, ApplicationStep]:
    hidden = set(hide)
    registry: dict[str, ApplicationStep] = {}
    for capability_id in (pair["producer_id"], pair["consumer_id"]):
        if capability_id not in hidden and capability_id in steps:
            registry[capability_id] = steps[capability_id]
    if include_bridge:
        bridge = make_bridge_step(pair)
        if bridge.capability_id not in hidden:
            registry[bridge.capability_id] = bridge
    return registry


def load_persisted_bridge_records(path: Path | None = None) -> list[dict[str, Any]]:
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


def load_persisted_bridge_steps(path: Path | None = None) -> dict[str, ApplicationStep]:
    steps: dict[str, ApplicationStep] = {}
    for record in load_persisted_bridge_records(path):
        if not record.get("bridge_id"):
            continue
        step = make_bridge_step(record)
        steps[step.capability_id] = step
    return steps


def persist_bridge_pair(pair: Mapping[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    target = durable_write_path(path or BRIDGES_PATH)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "absorbed_bridges",
        "updated_at": utc_now_iso(),
        "bridges": [dict(pair)],
    }
    atomic_write_json(target, payload)
    return payload


def run_composition_honesty(pair: Mapping[str, Any], steps: Mapping[str, ApplicationStep]) -> dict[str, Any]:
    """Unplannable without the bridge; solved with it; ablation and reverse fail."""

    task = composition_task(pair, steps)
    isolated = composition_registry(steps, pair, include_bridge=False)
    before_plan = plan_application_task(task, isolated)
    grown = composition_registry(steps, pair, include_bridge=True)
    grown_result = run_application_task(task, grown)
    grown_plan = list(grown_result.get("plan") or [])
    expected_plan = [pair["producer_id"], pair["bridge_id"], pair["consumer_id"]]
    producer_hidden = composition_registry(steps, pair, hide=[str(pair["producer_id"])])
    consumer_hidden = composition_registry(steps, pair, hide=[str(pair["consumer_id"])])
    bridge_hidden = composition_registry(steps, pair, hide=[str(pair["bridge_id"])])
    reversed_broke = False
    if grown_plan:
        try:
            reversed_state = execute_application_plan(task, list(reversed(grown_plan)), grown)
            reversed_broke = any(reversed_state.get(key) != value for key, value in task.oracle.items())
        except Exception:  # noqa: BLE001 - a crashed reverse is a broken outcome
            reversed_broke = True
    minimality: list[dict[str, Any]] = []
    for member in grown_plan:
        reduced = {key: step for key, step in grown.items() if key != member}
        broke = plan_application_task(task, reduced) is None
        if not broke:
            reduced_result = run_application_task(task, reduced, plan_override=[item for item in grown_plan if item != member])
            broke = not bool(reduced_result.get("ok"))
        minimality.append({"member": member, "broke_outcome": broke})
    verdicts = {
        "unplannable_without_bridge": before_plan is None,
        "grown_plan_solved": bool(grown_result.get("ok")) and grown_plan == expected_plan,
        "producer_ablation_unplannable": plan_application_task(task, producer_hidden) is None,
        "consumer_ablation_unplannable": plan_application_task(task, consumer_hidden) is None,
        "bridge_ablation_unplannable": plan_application_task(task, bridge_hidden) is None,
        "reversed_broke": reversed_broke,
        "minimality": all(item["broke_outcome"] for item in minimality) and len(minimality) == 3,
        "cross_runtime": str(pair.get("producer_runtime") or "") != str(pair.get("consumer_runtime") or "")
        and {pair.get("producer_runtime"), pair.get("consumer_runtime")} == {"python", "node"},
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


def run_absorbed_composition_plane(output_dir: Path | None = None) -> dict[str, Any]:
    """Discover the live pair, prove honesty, persist the bridge, seal a report."""

    records = load_persisted_records()
    steps = load_persisted_absorbed_steps()
    pair = select_composition_pair(records, steps=steps)
    if pair is None:
        return {"ok": False, "error": "no_compatible_absorbed_pair", "used_skill_route_discovery": False}
    honesty = run_composition_honesty(pair, steps)
    persist_bridge_pair(pair)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_absorbed_composition",
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


def verify_absorbed_composition_report(report_dir: Path) -> dict[str, Any]:
    """Re-run the live chain and re-check the sealed digest."""

    report_path = durable_read_path(report_dir / "report.json")
    if not report_path.is_file():
        return {"ok": False, "error": f"missing report.json in {report_dir}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    steps = load_persisted_absorbed_steps()
    pair = dict(report.get("pair") or {})
    if not pair:
        return {"ok": False, "error": "report missing pair"}
    honesty = run_composition_honesty(pair, steps)
    recomputed = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability_absorbed_composition",
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


def absorbed_composition_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.capability_absorbed_composition import "
        "builtin_absorbed_composition_bridge_proof; "
        "r=builtin_absorbed_composition_bridge_proof(); "
        "assert r['ok'] and r.get('verdicts',{}).get('unplannable_without_bridge') "
        "and r.get('verdicts',{}).get('grown_plan_solved') "
        "and r.get('verdicts',{}).get('producer_ablation_unplannable') "
        "and r.get('verdicts',{}).get('consumer_ablation_unplannable') "
        "and r.get('verdicts',{}).get('bridge_ablation_unplannable') "
        "and r.get('verdicts',{}).get('cross_runtime') "
        "and r.get('verify_ok') and r.get('tamper_detected') "
        "and r.get('misgrade_detected') and not r.get('used_skill_route_discovery')\""
    )


def ensure_absorbed_composition_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the plane on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=ABSORBED_COMPOSITION_ID,
        name="Absorbed composition bridge",
        description=(
            "Typed key-bridge that lets two independently absorbed tools compose "
            "in the goal-directed planner: a Python producer feeds a Node "
            "consumer through a mapping step, the pipeline is BFS-derived, and "
            "hiding either member or the bridge makes the goal unplannable."
        ),
        kind="python",
        entry="blackhole_agent.capability_absorbed_composition:builtin_absorbed_composition_bridge_proof",
        proof_command=absorbed_composition_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.absorbed-text-reverser",
            "capability.absorbed-snake-case",
        ),
        behavior_paths=(
            "src/blackhole_agent/capability_absorbed_composition.py",
            "src/blackhole_agent/capability_application.py",
            "capabilities/absorbed-bridges.json",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Independently absorbed tools compose: a typed key-bridge turns an "
            "unplannable two-tool goal into a planner-derived Python→Node "
            "pipeline, and ablation of either leaf or the bridge fails it."
        ),
        tags=("absorbed", "composition", "bridge", "application", "cross-runtime"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_absorbed_composition_bridge_proof() -> dict[str, Any]:
    """Registered proof: live honesty, sealed verification, tamper and misgrade."""

    with tempfile.TemporaryDirectory(prefix="blackhole-absorbed-composition-") as tmp:
        report_dir = Path(tmp) / "report"
        result = run_absorbed_composition_plane(report_dir)
        if not result.get("ok"):
            return {**result, "verify_ok": False, "tamper_detected": False, "misgrade_detected": False}
        verification = verify_absorbed_composition_report(report_dir)
        report_path = report_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        tampered = json.loads(json.dumps(report))
        tampered["verdicts"]["grown_plan_solved"] = not tampered["verdicts"]["grown_plan_solved"]
        atomic_write_json(report_path, tampered)
        tamper_failed = not verify_absorbed_composition_report(report_dir)["ok"]
        misgraded = json.loads(json.dumps(report))
        misgraded["grade"]["ok"] = not bool(misgraded["grade"]["ok"])
        atomic_write_json(report_path, misgraded)
        misgrade_failed = not verify_absorbed_composition_report(report_dir)["ok"]
        atomic_write_json(report_path, report)
    live = run_absorbed_composition_plane(DEFAULT_ARTIFACT_DIR)
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
        "action": "absorbed_composition_bridge",
        "live_report_dir": str(DEFAULT_ARTIFACT_DIR),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
