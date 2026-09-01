"""Drive a first-class SQLite tool through a schema-gated transactional workflow.

Tool routing already fails missions that require ``sqlite``: hosted database
plugins stay on the unsupported MCP provider, and no first-party SQLite
provider is executable. Unbound therefore cannot open a database file, apply
a schema, or seal a transactional query.

This module closes that hole:

- advertise a ``sqlite`` provider tool that stays fail-closed until opted in
- drive open / migrate / insert / commit / query against a real sqlite3 file
- keep a missing-file client so the open hole stays falsifiable
- refuse writes until the schema migration has been applied
- roll back an uncommitted insert so durability stays falsifiable
- seal a digest-chained actuation trace
- bind this family as the next diversity-catalog successor after GitHub
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
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
    SQLITE_TOOL_PROVIDER,
    UNSUPPORTED_TOOL_ROUTE,
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
    route_tool_descriptor,
    sqlite_tool_descriptor,
)

SCHEMA_VERSION = 1
SQLITE_ACTUATION_ID = "capability.sqlite-actuation"
REPO_ROOT = Path(__file__).resolve().parents[2]
UNLOCK_TOKEN = "blackhole-sqlite"
SENTINEL = "BH-SQLITE-OK"
DEFAULT_DB_NAME = "beacon.sqlite"
SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version INTEGER PRIMARY KEY,"
    " applied_at TEXT NOT NULL"
    ");"
    "CREATE TABLE IF NOT EXISTS beacons ("
    " id INTEGER PRIMARY KEY,"
    " token TEXT NOT NULL UNIQUE,"
    " sealed INTEGER NOT NULL DEFAULT 0"
    ");"
)

SQLITE_ACTUATION_DONE_WHEN = (
    f"capability_exists:{SQLITE_ACTUATION_ID};"
    f"capability_proved:{SQLITE_ACTUATION_ID};"
    "no_skill_route"
)
SQLITE_ACTUATION_GOAL = (
    "Repair SQLite schema-gated durable storage: hosted database tools remain "
    "unsupported so a schema cannot be applied and a sealed transactional query "
    "cannot be produced. A missing database file stays forbidden; fail-closed "
    "routing never opts the sqlite provider in."
)


class SqliteActuationError(RuntimeError):
    """Raised when the database session or fixture misbehaves."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class SqliteSession:
    """File-gated sqlite3 session: open, migrate, insert, commit, query."""

    def __init__(self, db_path: Path, *, create_if_missing: bool = True) -> None:
        self.db_path = Path(db_path)
        self.create_if_missing = bool(create_if_missing)
        self.conn: sqlite3.Connection | None = None
        self.schema_applied = False
        self.history: list[dict[str, Any]] = []

    def _forbidden(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": 403,
            "error": reason,
            "token": "",
            "sentinel": "",
            "row_count": 0,
        }

    def _require_conn(self) -> dict[str, Any] | None:
        if self.conn is None:
            return {
                "ok": False,
                "status": 409,
                "error": "not_open",
                "token": "",
                "sentinel": "",
                "row_count": 0,
            }
        return None

    def open(self) -> dict[str, Any]:
        existed_before = self.db_path.exists()
        if not existed_before and not self.create_if_missing:
            return self._forbidden("missing_database")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=DELETE")
        return {
            "ok": True,
            "status": 200,
            "path": str(self.db_path),
            "created": not existed_before,
            "journal_mode": "delete",
        }

    def migrate(self) -> dict[str, Any]:
        blocked = self._require_conn()
        if blocked is not None:
            return blocked
        assert self.conn is not None
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (1, ?)",
            (utc_now_iso(),),
        )
        self.conn.commit()
        self.schema_applied = True
        versions = [
            int(row[0])
            for row in self.conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
        return {
            "ok": True,
            "status": 200,
            "schema_applied": True,
            "versions": versions,
        }

    def insert(self, token: str = SENTINEL) -> dict[str, Any]:
        blocked = self._require_conn()
        if blocked is not None:
            return blocked
        assert self.conn is not None
        wanted = str(token or SENTINEL)
        try:
            self.conn.execute(
                "INSERT INTO beacons(token, sealed) VALUES (?, 1)",
                (wanted,),
            )
        except sqlite3.OperationalError:
            return self._forbidden("schema_gated")
        except sqlite3.IntegrityError as error:
            return {
                "ok": False,
                "status": 409,
                "error": "duplicate_token",
                "detail": str(error),
                "token": wanted,
                "sentinel": "",
                "row_count": 0,
            }
        return {
            "ok": True,
            "status": 201,
            "token": wanted,
            "pending": True,
            "schema_applied": self.schema_applied,
        }

    def commit(self) -> dict[str, Any]:
        blocked = self._require_conn()
        if blocked is not None:
            return blocked
        assert self.conn is not None
        self.conn.commit()
        return {"ok": True, "status": 200, "committed": True}

    def rollback(self) -> dict[str, Any]:
        blocked = self._require_conn()
        if blocked is not None:
            return blocked
        assert self.conn is not None
        self.conn.rollback()
        return {"ok": True, "status": 200, "rolled_back": True}

    def query(self, token: str = SENTINEL) -> dict[str, Any]:
        blocked = self._require_conn()
        if blocked is not None:
            return blocked
        assert self.conn is not None
        wanted = str(token or SENTINEL)
        try:
            rows = list(
                self.conn.execute(
                    "SELECT token, sealed FROM beacons WHERE token = ?",
                    (wanted,),
                )
            )
        except sqlite3.OperationalError:
            return self._forbidden("schema_gated")
        found = rows[0][0] if rows else ""
        sealed = bool(rows[0][1]) if rows else False
        return {
            "ok": True,
            "status": 200,
            "token": found,
            "sentinel": SENTINEL if found == SENTINEL and sealed else "",
            "row_count": len(rows),
            "sealed": sealed,
        }

    def close(self) -> dict[str, Any]:
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = None
        return {"ok": True, "status": 200, "closed": True, "path": str(self.db_path)}


def call_sqlite_tool(session: SqliteSession, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch one sqlite tool call against an open database session."""

    action = str(arguments.get("action") or "").strip()
    token = str(arguments.get("token") or SENTINEL)
    if action == "open":
        result = session.open()
    elif action == "migrate":
        result = session.migrate()
    elif action == "insert":
        result = session.insert(token)
    elif action == "commit":
        result = session.commit()
    elif action == "rollback":
        result = session.rollback()
    elif action == "query":
        result = session.query(token)
    elif action == "close":
        result = session.close()
    else:
        raise SqliteActuationError(f"unsupported sqlite action: {action!r}")
    payload = {"action": action, **result}
    session.history.append({"action": action, "status": int(payload.get("status") or 0)})
    return payload


def independent_beacon_row(db_path: Path, token: str = SENTINEL) -> dict[str, Any]:
    """Read the beacon table through a fresh sqlite3 connection."""

    path = Path(db_path)
    if not path.is_file():
        return {"ok": False, "error": "missing_database", "token": "", "row_count": 0}
    conn = sqlite3.connect(str(path))
    try:
        try:
            rows = list(
                conn.execute("SELECT token, sealed FROM beacons WHERE token = ?", (token,))
            )
        except sqlite3.OperationalError as error:
            return {
                "ok": False,
                "error": "schema_gated",
                "detail": str(error),
                "token": "",
                "row_count": 0,
            }
    finally:
        conn.close()
    found = str(rows[0][0]) if rows else ""
    return {
        "ok": True,
        "token": found,
        "sentinel": SENTINEL if found == SENTINEL else "",
        "row_count": len(rows),
        "sealed": bool(rows[0][1]) if rows else False,
    }


def run_sqlite_workflow(
    *,
    create_if_missing: bool = True,
    skip_schema: bool = False,
    skip_commit: bool = False,
    output_dir: Path | None = None,
    db_name: str = DEFAULT_DB_NAME,
) -> dict[str, Any]:
    """Execute the schema-gated transactional workflow and seal a trace."""

    descriptor = sqlite_tool_descriptor()
    decision = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SQLITE_TOOL_PROVIDER),
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
        raise SqliteActuationError(f"sqlite tool did not route executable: {decision.reasons}")

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="sqlite-live-"))
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / db_name
    session = SqliteSession(db_path, create_if_missing=create_if_missing)
    calls: list[dict[str, Any]] = [{"action": "open"}]
    if not skip_schema:
        calls.append({"action": "migrate"})
    calls.append({"action": "insert", "token": SENTINEL})
    if skip_commit:
        calls.append({"action": "rollback"})
    else:
        calls.append({"action": "commit"})
    calls.extend([{"action": "query", "token": SENTINEL}, {"action": "close"}])

    results: list[dict[str, Any]] = []
    try:
        for arguments in calls:
            try:
                results.append(call_sqlite_tool(session, arguments))
            except SqliteActuationError as error:
                results.append({"action": arguments["action"], "error": str(error)})
                break
            if int(results[-1].get("status") or 0) >= 400:
                break
    finally:
        session.close()

    query_result = next((item for item in results if item.get("action") == "query"), {})
    insert_result = next((item for item in results if item.get("action") == "insert"), {})
    independent = independent_beacon_row(db_path)
    sentinel = str(query_result.get("sentinel") or "")
    sealed = bool(
        decision.executable
        and create_if_missing
        and not skip_schema
        and not skip_commit
        and sentinel == SENTINEL
        and independent.get("sentinel") == SENTINEL
        and int(independent.get("row_count") or 0) == 1
        and db_path.is_file()
    )
    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "sqlite_live_execution_trace",
        "recorded_at": utc_now_iso(),
        "create_if_missing": create_if_missing,
        "skip_schema": skip_schema,
        "skip_commit": skip_commit,
        "db_path": str(db_path),
        "routing": routing,
        "routing_digest": _digest(routing),
        "calls": calls,
        "results": results,
        "result_digest": _digest(results),
        "independent": independent,
        "independent_digest": _digest(independent),
        "sentinel": sentinel,
        "schema_applied": bool(insert_result.get("schema_applied") or session.schema_applied),
        "row_count": int(query_result.get("row_count") or 0),
        "db_exists": db_path.is_file(),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}
    from blackhole_agent.capability_compounder import atomic_write_json

    atomic_write_json(out / "execution.json", trace)
    final = results[-1] if results else {}
    return {
        "ok": sealed,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "db_path": str(db_path),
        "sentinel": sentinel,
        "final_status": int(final.get("status") or 0),
        "error": str(final.get("error") or insert_result.get("error") or ""),
        "schema_applied": bool(trace_body["schema_applied"]),
        "row_count": int(query_result.get("row_count") or 0),
        "independent_sentinel": str(independent.get("sentinel") or ""),
        "db_exists": db_path.is_file(),
        "skip_schema": skip_schema,
        "skip_commit": skip_commit,
        "create_if_missing": create_if_missing,
    }


def verify_sqlite_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed SQLite trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    routing = trace.get("routing") or {}
    independent = trace.get("independent") or {}
    db_path = Path(str(trace.get("db_path") or ""))
    live_row = independent_beacon_row(db_path) if db_path.is_file() else {"ok": False, "sentinel": ""}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "routing_digest": _digest(routing) == trace.get("routing_digest"),
        "result_digest": _digest(trace.get("results")) == trace.get("result_digest"),
        "independent_digest": _digest(independent) == trace.get("independent_digest"),
        "routing_executable": routing.get("executable") is True
        and routing.get("route") == EXECUTABLE_TOOL_ROUTE,
        "sentinel_recorded": str(trace.get("sentinel") or "") == SENTINEL,
        "independent_recorded": str(independent.get("sentinel") or "") == SENTINEL,
        "live_row_matches": str(live_row.get("sentinel") or "") == SENTINEL,
        "db_exists": bool(trace.get("db_exists")) and db_path.is_file(),
        "schema_applied": trace.get("schema_applied") is True,
        "one_beacon": int(trace.get("row_count") or 0) == 1,
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def sqlite_actuation_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.sqlite_actuation import "
        "builtin_sqlite_actuation_proof; r=builtin_sqlite_actuation_proof(); "
        "assert r['ok'] and r.get('action')=='sqlite_actuation' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_sqlite_actuation_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=SQLITE_ACTUATION_ID,
        name="First-class SQLite schema-gated durable storage",
        description=(
            "Missions that require a SQLite tool can opt the sqlite provider in, "
            "open a database file, apply a schema migration, and seal a "
            "digest-chained transactional query. Default routing stays fail-closed; "
            "a missing database file keeps the open hole falsifiable, and writes "
            "stay schema-gated. An uncommitted insert rolls back."
        ),
        kind="python",
        entry="blackhole_agent.sqlite_actuation:builtin_sqlite_actuation_proof",
        proof_command=sqlite_actuation_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.github-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/sqlite_actuation.py",
            "src/blackhole_agent/tool_routing.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A required SQLite tool is executable after explicit provider opt-in: "
            "Unbound opens a real sqlite3 file, applies a schema migration, "
            "commits a beacon row, independently re-reads the sentinel, and binds "
            "this family as the next diversity-catalog successor once GitHub "
            "actuation is proved. Missing files, skipped schemas, and rolled-back "
            "inserts stay fail-closed."
        ),
        tags=("sqlite", "schema", "transaction", "actuation", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T035643Z-23da7e76",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_sqlite_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: opted-in SQLite actuation seals a schema-gated query."""

    from blackhole_agent.github_actuation import GITHUB_ACTUATION_GOAL, GITHUB_ACTUATION_ID
    from blackhole_agent.gmail_actuation import GMAIL_ACTUATION_GOAL, GMAIL_ACTUATION_ID
    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import capability_family

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = SQLITE_ACTUATION_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(SQLITE_ACTUATION_GOAL) == (
        SQLITE_ACTUATION_ID,
    )
    checks["github_goal_is_not_sqlite"] = leftover_marker_ids(GITHUB_ACTUATION_GOAL) == (
        GITHUB_ACTUATION_ID,
    )
    checks["gmail_goal_is_not_sqlite"] = leftover_marker_ids(GMAIL_ACTUATION_GOAL) == (
        GMAIL_ACTUATION_ID,
    )
    checks["sqlite_goal_is_not_github"] = GITHUB_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["sqlite_goal_is_not_gmail"] = GMAIL_ACTUATION_ID not in leftover_marker_ids(
        SQLITE_ACTUATION_GOAL
    )
    checks["github_marker_stays_github"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        GITHUB_ACTUATION_GOAL
    )
    checks["gmail_marker_stays_gmail"] = SQLITE_ACTUATION_ID not in leftover_marker_ids(
        GMAIL_ACTUATION_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_sqlite"] = (
        len(catalog) > 25
        and catalog[25]["id"] == SQLITE_ACTUATION_ID
        and catalog[24]["id"] == GITHUB_ACTUATION_ID
    )
    checks["family_is_sqlite"] = "sqlite" in capability_family(SQLITE_ACTUATION_GOAL)
    checks["family_is_not_git_publication"] = "git-publication" not in capability_family(
        SQLITE_ACTUATION_GOAL
    )
    checks["family_is_not_browser"] = "browser" not in capability_family(SQLITE_ACTUATION_GOAL)
    checks["family_is_not_timeout"] = "timeout" not in capability_family(SQLITE_ACTUATION_GOAL)

    mcp_sqlite = ToolDescriptor(name="remote_sqlite", provider=MCP_TOOL_PROVIDER)
    default_mcp = route_tool_descriptor(mcp_sqlite)
    checks["naive_mcp_sqlite_is_unsupported"] = (
        default_mcp.route == UNSUPPORTED_TOOL_ROUTE
        and default_mcp.reasons == (f"unsupported_provider:{MCP_TOOL_PROVIDER}",)
    )

    descriptor = sqlite_tool_descriptor()
    default_sqlite = route_tool_descriptor(descriptor)
    opted = route_tool_descriptor(
        descriptor,
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SQLITE_TOOL_PROVIDER),
    )
    checks["default_sqlite_provider_is_unsupported"] = (
        default_sqlite.route == UNSUPPORTED_TOOL_ROUTE
        and f"unsupported_provider:{SQLITE_TOOL_PROVIDER}" in default_sqlite.reasons
    )
    checks["opted_in_sqlite_is_executable"] = (
        opted.executable is True and opted.route == EXECUTABLE_TOOL_ROUTE
    )

    naive_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), mcp_sqlite],
        required_tool_names=("local_memory", "sqlite"),
    )
    checks["naive_preflight_missing_sqlite"] = (
        naive_preflight["ok"] is False
        and naive_preflight["missing_required_tool_names"] == ["sqlite"]
    )
    live_preflight = build_tool_routing_preflight(
        [local_memory_tool_descriptor(), descriptor],
        required_tool_names=("local_memory", "sqlite"),
        executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, SQLITE_TOOL_PROVIDER),
    )
    checks["opted_in_preflight_ok"] = (
        live_preflight["ok"] is True
        and "sqlite" in live_preflight["executable_tool_names"]
        and not live_preflight["missing_required_tool_names"]
    )

    with tempfile.TemporaryDirectory(prefix="sqlite-actuation-") as tmp:
        root = Path(tmp)
        missing = run_sqlite_workflow(
            create_if_missing=False,
            output_dir=root / "missing",
        )
        unmigrated = run_sqlite_workflow(skip_schema=True, output_dir=root / "unmigrated")
        rolled = run_sqlite_workflow(skip_commit=True, output_dir=root / "rolled")
        live = run_sqlite_workflow(output_dir=root / "live")
        verify = verify_sqlite_trace(Path(live["output_dir"]))
        clone = root / "tampered"
        shutil.copytree(live["output_dir"], clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["sentinel"] = "forged"
        from blackhole_agent.capability_compounder import atomic_write_json

        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_sqlite_trace(clone)
        checks["naive_without_file_is_forbidden"] = (
            missing["ok"] is False
            and missing["sentinel"] == ""
            and missing["final_status"] == 403
            and missing["error"] == "missing_database"
            and missing["db_exists"] is False
        )
        checks["unmigrated_insert_is_forbidden"] = (
            unmigrated["ok"] is False
            and unmigrated["final_status"] == 403
            and unmigrated["error"] == "schema_gated"
            and unmigrated["schema_applied"] is False
        )
        checks["uncommitted_insert_rolls_back"] = (
            rolled["ok"] is False
            and rolled["sentinel"] == ""
            and rolled["independent_sentinel"] == ""
            and rolled["row_count"] == 0
            and rolled["schema_applied"] is True
            and rolled["db_exists"] is True
        )
        checks["workflow_extracts_sentinel"] = live["sentinel"] == SENTINEL
        checks["workflow_commits_independent_row"] = live["independent_sentinel"] == SENTINEL
        checks["workflow_writes_sqlite_file"] = live["db_exists"] is True
        checks["file_schema_and_commit_are_required"] = (
            missing["ok"] is False
            and unmigrated["ok"] is False
            and rolled["ok"] is False
            and live["ok"] is True
        )
        checks["sealed_trace_verifies"] = verify["ok"] is True
        checks["tampered_trace_fails"] = tampered["ok"] is False

    with tempfile.TemporaryDirectory(prefix="sqlite-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != SQLITE_ACTUATION_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_sqlite"] = (
        live_goal == SQLITE_ACTUATION_GOAL
        and SQLITE_ACTUATION_ID in live_done
        and live_source == "genesis_bind_sqlite"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_sqlite_actuation_capability()
    return {
        "ok": ok,
        "action": "sqlite_actuation",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": SQLITE_ACTUATION_GOAL,
        "done_when": SQLITE_ACTUATION_DONE_WHEN,
    }
