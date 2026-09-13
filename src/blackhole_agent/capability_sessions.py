"""Durable, interactive, cancellable goal sessions on the invocation plane.

``POST /solve`` answers a declarative goal in one stateless shot: the client
must already hold every state key the derived program needs, the goal dies
with the connection, and a long-running tool cannot be stopped without
killing the server. Goal sessions close those three gaps:

- **Elicitation.** When no program covers the goal from the supplied state
  alone, an elicitation planner searches for the minimal set of *external*
  state keys (``requires`` keys no invocable capability ever ``provides``)
  that would unlock a real program. The session answers ``awaiting_input``
  naming exactly those keys — with the capability that needs each one — and
  spawns no subprocess until the client supplies them.
- **Durability.** Every session is a JSON record under
  ``artifacts/capability-service-sessions/`` rewritten atomically on each
  transition (created, input accepted, step completed with its response
  digest, solved, failed, cancelled, interrupted, resumed). A server
  restart recovers records from disk: sessions that were mid-execution when
  the process died become ``interrupted`` and can be resumed from their
  persisted threaded state via ``POST /sessions/{id}/resume``; sessions
  awaiting input simply keep waiting. The ``plan_digest`` uses the same
  binding formula as ``POST /solve``, so an outcome completed across a
  restart digests identically to a one-shot solve.
- **Cancellation.** Execution runs on a background thread with a per-session
  cancel event threaded into :func:`run_captured_process`; ``DELETE
  /sessions/{id}`` sets the event and the running tool's entire owned
  process tree (Windows job object or POSIX process group) is terminated —
  not just the launcher.

Every state transition recomputes a ``session_digest`` over the goal,
initial state, transition kinds, and per-step response digests (timestamps
excluded), so a client can verify it is looking at the same session history
after a restart.
"""

from __future__ import annotations

import heapq
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso
from blackhole_agent.capability_service import (
    SOLVE_MAX_STEPS,
    InvocationError,
    _digest,
    invoke_capability,
    load_invocable_capabilities,
)
from blackhole_agent.process_capture import ProcessCancelled

SESSION_SCHEMA_VERSION = 1
SESSIONS_DIR_NAME = "capability-service-sessions"
# Elicitation is bounded: a session may ask for at most this many external
# state keys, and the search expands at most this many planner states before
# honestly reporting the goal unsolvable.
MAX_ELICITED_KEYS = 4
MAX_PLANNER_EXPANSIONS = 20000

TERMINAL_STATUSES = frozenset({"solved", "unsolvable", "cancelled", "failed"})


def sessions_dir(root: Path) -> Path:
    return Path(root).resolve() / "artifacts" / SESSIONS_DIR_NAME


def _session_path(root: Path, session_id: str) -> Path:
    return sessions_dir(root) / f"{session_id}.json"


def external_state_keys(invocable: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """Requires keys no invocable capability provides — only a client can supply them."""

    provided: set[str] = set()
    required: set[str] = set()
    for item in invocable.values():
        provided |= set(item["provides"])
        required |= set(item["requires"])
    return required - provided


def plan_goal_with_elicitation(
    invocable: Mapping[str, Mapping[str, Any]],
    initial_keys: set[str],
    goal_keys: Sequence[str],
    *,
    max_steps: int = SOLVE_MAX_STEPS,
    max_elicited: int = MAX_ELICITED_KEYS,
) -> dict[str, Any] | None:
    """Minimal program over the invocable ledger, eliciting external keys.

    Dijkstra-ordered search (fewest elicited keys, then fewest steps) over
    monotone key-set growth. A capability is applicable when every
    ``requires`` key is either already available or an external key the
    client can be asked for; applying it threads the elicited keys into the
    available set as if the client had supplied them. Goal keys that are
    themselves external are elicited directly. Returns
    ``{"program": [...], "elicited_keys": [...], "key_consumers": {...}}``
    or ``None`` when no bounded program exists — an honest unsolvable.
    """

    goal = set(goal_keys)
    externals = external_state_keys(invocable)
    start = frozenset(initial_keys)
    # (elicited count, step count, tiebreak, available, program, elicited)
    queue: list[tuple[int, int, int, frozenset[str], tuple[str, ...], frozenset[str]]] = []
    counter = 0
    heapq.heappush(queue, (0, 0, counter, start, (), frozenset()))
    best_elicited: dict[frozenset[str], int] = {start: 0}
    expansions = 0

    def finish(
        available: frozenset[str], program: tuple[str, ...], elicited: frozenset[str]
    ) -> dict[str, Any] | None:
        direct = goal - set(available)
        if not direct <= externals:
            return None
        total_elicited = elicited | frozenset(direct)
        if len(total_elicited) > max_elicited:
            return None
        key_consumers: dict[str, str] = {}
        produced = set(start)
        for capability_id in program:
            item = invocable[capability_id]
            for key in item["requires"]:
                if key in total_elicited and key not in produced and key not in key_consumers:
                    key_consumers[key] = capability_id
            produced |= set(item["provides"])
        for key in sorted(direct):
            key_consumers.setdefault(key, "goal")
        return {
            "program": list(program),
            "elicited_keys": sorted(total_elicited),
            "key_consumers": key_consumers,
        }

    first = finish(start, (), frozenset())
    if first is not None:
        return first
    while queue:
        _, _, _, available, program, elicited = heapq.heappop(queue)
        expansions += 1
        if expansions > MAX_PLANNER_EXPANSIONS:
            return None
        if len(program) >= max_steps:
            continue
        for capability_id in sorted(invocable):
            if capability_id in program:
                continue
            item = invocable[capability_id]
            missing = set(item["requires"]) - set(available)
            if not missing <= externals:
                continue
            new_elicited = elicited | frozenset(missing)
            if len(new_elicited) > max_elicited:
                continue
            new_available = available | frozenset(missing) | frozenset(item["provides"])
            new_program = program + (capability_id,)
            solved = finish(new_available, new_program, new_elicited)
            if solved is not None:
                return solved
            if best_elicited.get(new_available, max_elicited + 1) <= len(new_elicited):
                continue
            best_elicited[new_available] = len(new_elicited)
            counter += 1
            heapq.heappush(
                queue,
                (len(new_elicited), len(new_program), counter, new_available, new_program, new_elicited),
            )
    return None


def _compute_session_digest(record: Mapping[str, Any]) -> str:
    return _digest(
        {
            "session_id": record["session_id"],
            "goal": record["goal"],
            "initial_state": record["initial_state"],
            "status": record["status"],
            "plan": record["plan"],
            "outcome": record["outcome"],
            "transitions": [
                {
                    "seq": transition["seq"],
                    "kind": transition["kind"],
                    "detail": transition.get("detail"),
                }
                for transition in record["transitions"]
            ],
        }
    )


def _plan_digest(record: Mapping[str, Any]) -> str:
    return _digest(
        {
            "initial_state": record["initial_state"],
            "goal": record["goal"],
            "plan": record["plan"],
            "steps": [
                {"capability_id": step["capability_id"], "response_digest": step["response_digest"]}
                for step in record["steps"]
            ],
            "outcome": record["outcome"],
        }
    )


class SessionManager:
    """Owns session records, execution threads, and cancel events."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._lock = threading.Lock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    # -- persistence ------------------------------------------------------

    def _load(self, session_id: str) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id.strip() or "/" in session_id:
            raise InvocationError(404, f"unknown session: {session_id!r}")
        path = _session_path(self.root, session_id)
        if not path.is_file():
            raise InvocationError(404, f"unknown session: {session_id}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise InvocationError(409, f"session {session_id} has an unsupported schema")
        return record

    def _persist(self, record: dict[str, Any]) -> dict[str, Any]:
        record["updated_at"] = utc_now_iso()
        record["session_digest"] = _compute_session_digest(record)
        atomic_write_json(_session_path(self.root, record["session_id"]), record)
        return record

    def _transition(self, record: dict[str, Any], kind: str, detail: Any = None) -> None:
        record["transitions"].append(
            {
                "seq": len(record["transitions"]),
                "kind": kind,
                "at": utc_now_iso(),
                "detail": detail,
            }
        )

    # -- recovery ---------------------------------------------------------

    def recover(self) -> list[str]:
        """Mark sessions that were mid-execution at server death as interrupted."""

        recovered: list[str] = []
        directory = sessions_dir(self.root)
        if not directory.is_dir():
            return recovered
        for path in sorted(directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if record.get("schema_version") != SESSION_SCHEMA_VERSION:
                continue
            if record.get("status") == "running":
                record["status"] = "interrupted"
                self._transition(record, "interrupted", "server stopped while execution ran")
                self._persist(record)
                recovered.append(record["session_id"])
        return recovered

    # -- API --------------------------------------------------------------

    def list_sessions(self) -> dict[str, Any]:
        items = []
        directory = sessions_dir(self.root)
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                items.append(
                    {
                        "session_id": record.get("session_id"),
                        "status": record.get("status"),
                        "goal": record.get("goal"),
                        "session_digest": record.get("session_digest"),
                    }
                )
        return {"ok": True, "sessions": items, "count": len(items)}

    def get_session(self, session_id: str) -> dict[str, Any]:
        record = self._load(session_id)
        return {"ok": True, "session": record}

    def create_session(self, initial_state: Any, goal: Any) -> dict[str, Any]:
        if not isinstance(initial_state, dict) or not all(
            isinstance(key, str) for key in initial_state
        ):
            raise InvocationError(422, "initial_state must be a JSON object keyed by state keys")
        if (
            not isinstance(goal, list)
            or not goal
            or not all(isinstance(key, str) and key.strip() for key in goal)
        ):
            raise InvocationError(422, "goal must be a non-empty list of state keys")
        goal_keys = list(dict.fromkeys(str(key).strip() for key in goal))
        invocable = load_invocable_capabilities(self.root)
        planned = plan_goal_with_elicitation(invocable, set(initial_state), goal_keys)
        session_id = uuid.uuid4().hex[:16]
        record: dict[str, Any] = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": session_id,
            "created_at": utc_now_iso(),
            "initial_state": dict(initial_state),
            "state": dict(initial_state),
            "goal": goal_keys,
            "status": "unsolvable",
            "plan": None,
            "elicited_keys": [],
            "pending_keys": [],
            "key_consumers": {},
            "steps": [],
            "outcome": None,
            "error": None,
            "transitions": [],
            "plan_digest": None,
        }
        self._transition(record, "created", {"goal": goal_keys})
        if planned is None:
            self._transition(record, "unsolvable", "no bounded capability program covers the goal")
            return {"ok": True, "session": self._persist(record)}
        record["plan"] = planned["program"]
        record["elicited_keys"] = planned["elicited_keys"]
        record["key_consumers"] = planned["key_consumers"]
        if planned["elicited_keys"]:
            record["status"] = "awaiting_input"
            record["pending_keys"] = planned["elicited_keys"]
            self._transition(record, "elicited", {"pending_keys": planned["elicited_keys"]})
            return {"ok": True, "session": self._persist(record)}
        self._transition(record, "planned", {"plan": planned["program"]})
        record["status"] = "running"
        self._persist(record)
        self._start_execution(record["session_id"])
        return {"ok": True, "session": record}

    def supply_input(self, session_id: str, supplied: Any) -> dict[str, Any]:
        record = self._load(session_id)
        if record["status"] != "awaiting_input":
            raise InvocationError(
                409, f"session {session_id} is {record['status']}, not awaiting input"
            )
        if not isinstance(supplied, dict) or not all(isinstance(key, str) for key in supplied):
            raise InvocationError(422, "input must be a JSON object keyed by state keys")
        pending = set(record["pending_keys"])
        keys = set(supplied)
        missing = sorted(pending - keys)
        extra = sorted(keys - pending)
        if missing or extra:
            problems = []
            if missing:
                problems.append(f"missing elicited keys: {missing}")
            if extra:
                problems.append(f"unexpected keys: {extra}")
            raise InvocationError(422, "; ".join(problems))
        record["state"].update(supplied)
        record["pending_keys"] = []
        self._transition(record, "input_accepted", {"keys": sorted(keys)})
        invocable = load_invocable_capabilities(self.root)
        planned = plan_goal_with_elicitation(invocable, set(record["state"]), record["goal"])
        if planned is None:
            record["status"] = "unsolvable"
            self._transition(record, "unsolvable", "no bounded capability program covers the goal")
            return {"ok": True, "session": self._persist(record)}
        record["plan"] = planned["program"]
        if planned["elicited_keys"]:
            record["elicited_keys"] = sorted(set(record["elicited_keys"]) | set(planned["elicited_keys"]))
            record["key_consumers"].update(
                {k: v for k, v in planned["key_consumers"].items() if k not in record["key_consumers"]}
            )
            record["pending_keys"] = planned["elicited_keys"]
            self._transition(record, "elicited", {"pending_keys": planned["elicited_keys"]})
            return {"ok": True, "session": self._persist(record)}
        self._transition(record, "planned", {"plan": planned["program"]})
        record["status"] = "running"
        self._persist(record)
        self._start_execution(session_id)
        return {"ok": True, "session": record}

    def resume_session(self, session_id: str) -> dict[str, Any]:
        record = self._load(session_id)
        if record["status"] != "interrupted":
            raise InvocationError(
                409, f"session {session_id} is {record['status']}, not interrupted"
            )
        record["status"] = "running"
        self._transition(record, "resumed", {"completed_steps": len(record["steps"])})
        self._persist(record)
        self._start_execution(session_id)
        return {"ok": True, "session": record}

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        record = self._load(session_id)
        status = record["status"]
        if status in TERMINAL_STATUSES:
            raise InvocationError(409, f"session {session_id} is already {status}")
        if status == "running":
            with self._lock:
                event = self._cancel_events.get(session_id)
            if event is None:
                record["status"] = "interrupted"
                self._transition(record, "interrupted", "execution thread was not live at cancel")
                return {"ok": True, "session": self._persist(record)}
            event.set()
            self._transition(record, "cancel_requested", None)
            return {"ok": True, "session": self._persist(record)}
        record["status"] = "cancelled"
        self._transition(record, "cancelled", f"cancelled while {status}")
        return {"ok": True, "session": self._persist(record)}

    # -- execution --------------------------------------------------------

    def _start_execution(self, session_id: str) -> None:
        event = threading.Event()
        with self._lock:
            self._cancel_events[session_id] = event
            thread = threading.Thread(
                target=self._execute, args=(session_id, event), daemon=True, name=f"session-{session_id}"
            )
            self._threads[session_id] = thread
            thread.start()

    def _execute(self, session_id: str, cancel_event: threading.Event) -> None:
        try:
            record = self._load(session_id)
            invocable = load_invocable_capabilities(self.root)
            state = dict(record["state"])
            program = list(record["plan"] or [])
            for capability_id in program[len(record["steps"]):]:
                item = invocable.get(capability_id)
                if item is None:
                    raise InvocationError(502, f"planned capability is no longer invocable: {capability_id}")
                step_input = {key: state[key] for key in item["requires"]}
                result = invoke_capability(
                    self.root, capability_id, step_input, cancel_event=cancel_event
                )
                state.update(result["output"])
                record["state"] = state
                record["steps"].append(
                    {
                        "capability_id": capability_id,
                        "input": step_input,
                        "output": result["output"],
                        "response_digest": result["response_digest"],
                    }
                )
                self._transition(
                    record,
                    "step_completed",
                    {"capability_id": capability_id, "response_digest": result["response_digest"]},
                )
                self._persist(record)
            outcome = {key: state[key] for key in record["goal"]}
            record["outcome"] = outcome
            record["status"] = "solved"
            record["plan_digest"] = _plan_digest(record)
            self._transition(record, "solved", {"plan_digest": record["plan_digest"]})
            self._persist(record)
        except ProcessCancelled:
            record = self._load(session_id)
            record["status"] = "cancelled"
            self._transition(record, "cancelled", "tool process tree terminated by cancel request")
            self._persist(record)
        except InvocationError as exc:
            record = self._load(session_id)
            record["status"] = "failed"
            record["error"] = exc.error
            self._transition(record, "failed", {"error": exc.error})
            self._persist(record)
        except Exception as exc:  # never leak a bare thread death
            record = self._load(session_id)
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            self._transition(record, "failed", {"error": record["error"]})
            self._persist(record)
        finally:
            with self._lock:
                self._cancel_events.pop(session_id, None)
                self._threads.pop(session_id, None)
