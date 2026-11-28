"""Durable, interactive goal sessions for the invocation service.

``POST /sessions`` chooses the shortest available plan among those needing the
fewest external inputs. An awaiting session names each missing key and its
first consumer. Supplying the keys to ``/sessions/{id}/input`` starts execution.
Transitions are saved under ``artifacts/capability-service-sessions/`` and
streamed on ``/sessions/{id}/events``. Servers sharing a root serialize edits
per session. The executing worker holds an OS lock until its final checkpoint.
After owner loss, explicit resume continues from completed steps. Workers
support process-tree cancellation, bounded reproof of quarantined steps, and
signed terminal notifications. The final plan digest matches a one-shot solve of the same steps.
"""

from __future__ import annotations

import heapq
import json
import queue
import re
import threading
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso
from blackhole_agent.capability_service import (
    SOLVE_MAX_HEALED,
    SOLVE_MAX_STEPS,
    InvocationError,
    _digest,
    heal_quarantined_blockers,
    invoke_capability,
    load_invocable_capabilities,
)
from blackhole_agent.durable_state import durable_read_path, durable_write_path
from blackhole_agent.file_guard import file_guard
from blackhole_agent.process_capture import ProcessCancelled
from blackhole_agent.session_notify import (
    RETRY_DELAYS_SECONDS,
    NotifyTargetError,
    deliver_session_notify,
    normalize_notify_spec,
    public_session_record,
    should_retry_notify,
)

SESSION_SCHEMA_VERSION = 1
SESSIONS_DIR_NAME = "capability-service-sessions"
# Per-request limits on distinct external inputs and expanded planner states.
MAX_ELICITED_KEYS = 4
MAX_PLANNER_EXPANSIONS = 20000

TERMINAL_STATUSES = frozenset({"solved", "unsolvable", "cancelled", "failed"})


def sessions_dir(root: Path) -> Path:
    return Path(root).resolve() / "artifacts" / SESSIONS_DIR_NAME


def _session_path(root: Path, session_id: str) -> Path:
    if (
        not isinstance(session_id, str)
        or session_id in {".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", session_id)
    ):
        raise InvocationError(404, f"unknown session: {session_id!r}")
    return sessions_dir(root) / f"{session_id}.json"


def _try_lease(path: Path) -> ExitStack | None:
    """The caller can transfer the open guard to a worker thread. Process exit releases it."""
    lease = ExitStack()
    try:
        lease.enter_context(file_guard(path, timeout=0, busy_message="session already owned"))
    except RuntimeError:
        return None
    return lease


class _CancelRequest:
    def __init__(self, record_path: Path):
        self.path = record_path.with_suffix(".cancel")

    def is_set(self) -> bool:
        return self.path.is_file()


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
    """Work backward from the goal, minimizing distinct user inputs, then steps.

    Prepending a tool replaces its outputs with its prerequisites. An external
    requirement can never disappear, so its count is a lower bound on every
    extension. The first complete plan popped from the heap has minimum cost.
    """
    external = external_state_keys(invocable)
    producers: dict[str, list[str]] = {}
    for name, item in invocable.items():
        for key in item["provides"]:
            producers.setdefault(key, []).append(name)
    goal = frozenset(goal_keys) - initial_keys
    initial_inputs = len(goal & external)
    if initial_inputs > max_elicited or goal.difference(external, producers):
        return None

    # A suffix is stored in execution order to break equal-cost ties consistently.
    frontier: list[tuple[int, int, tuple[str, ...], frozenset[str]]] = [(initial_inputs, 0, (), goal)]
    best: dict[frozenset[str], tuple[int, tuple[str, ...]]] = {goal: (0, ())}
    expansions = 0
    while frontier:
        _, depth, program, needed = heapq.heappop(frontier)
        if (depth, program) != best[needed]:
            continue
        if needed <= external:
            consumers: dict[str, str] = {}
            for name in program:
                for key in invocable[name]["requires"]:
                    if key in needed:
                        consumers.setdefault(key, name)
            for key in sorted(needed):
                consumers.setdefault(key, "goal")
            return {"program": list(program), "elicited_keys": sorted(needed), "key_consumers": consumers}
        if depth >= max_steps:
            continue
        if expansions >= MAX_PLANNER_EXPANSIONS:
            break
        expansions += 1
        candidates = {producer for key in needed for producer in producers.get(key, ())}
        for name in candidates:
            item = invocable[name]
            before = needed.difference(item["provides"]).union(item["requires"]) - initial_keys
            inputs_needed = len(before & external)
            if before >= needed or inputs_needed > max_elicited:
                continue
            # Suffixes with identical prerequisites admit exactly the same prefixes.
            rank = (depth + 1, (name,) + program)
            if before in best and best[before] <= rank:
                continue
            best[before] = rank
            heapq.heappush(frontier, (inputs_needed, *rank, before))
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


def session_event_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compact session snapshot for the live event stream."""

    transitions = list(record.get("transitions") or [])
    return {
        "session_id": record.get("session_id"),
        "status": record.get("status"),
        "goal": record.get("goal"),
        "pending_keys": list(record.get("pending_keys") or []),
        "key_consumers": dict(record.get("key_consumers") or {}),
        "elicited_keys": list(record.get("elicited_keys") or []),
        "plan": record.get("plan"),
        "outcome": record.get("outcome"),
        "error": record.get("error"),
        "session_digest": record.get("session_digest"),
        "transition": transitions[-1] if transitions else None,
    }


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
        self._event_listeners: dict[str, list[queue.Queue]] = {}

    # -- persistence ------------------------------------------------------

    def _load(self, session_id: str) -> dict[str, Any]:
        path = durable_read_path(_session_path(self.root, session_id))
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise InvocationError(404, f"unknown session: {session_id}") from exc
        if not isinstance(record, dict) or record.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise InvocationError(409, f"session {session_id} has an unsupported schema")
        if record.get("session_id") != session_id or not record.get("status"):
            raise InvocationError(409, f"session {session_id} has an invalid record")
        record.setdefault("healing", [])
        return record

    def _persist(self, record: dict[str, Any], *, notify: bool = True) -> dict[str, Any]:
        record["updated_at"] = utc_now_iso()
        record["session_digest"] = _compute_session_digest(record)
        atomic_write_json(_session_path(self.root, record["session_id"]), record)
        self._publish(record)
        if notify:
            self._maybe_notify(record)
        return record

    def _publish(self, record: Mapping[str, Any]) -> None:
        event = session_event_payload(record)
        with self._lock:
            listeners = list(self._event_listeners.get(str(record.get("session_id") or "")) or [])
        for listener in listeners:
            listener.put(event)

    def subscribe_events(self, session_id: str) -> queue.Queue:
        """Register a live listener and enqueue the current snapshot."""

        record = self._current(session_id)
        listener: queue.Queue = queue.Queue()
        with self._lock:
            self._event_listeners.setdefault(session_id, []).append(listener)
        listener.put(session_event_payload(record))
        return listener

    def unsubscribe_events(self, session_id: str, listener: queue.Queue) -> None:
        with self._lock:
            listeners = self._event_listeners.get(session_id)
            if not listeners:
                return
            try:
                listeners.remove(listener)
            except ValueError:
                return
            if not listeners:
                self._event_listeners.pop(session_id, None)

    def _transition(self, record: dict[str, Any], kind: str, detail: Any = None) -> None:
        record["transitions"].append(
            {
                "seq": len(record["transitions"]),
                "kind": kind,
                "at": utc_now_iso(),
                "detail": detail,
            }
        )

    # -- planning ---------------------------------------------------------

    def _plan_with_healing(
        self, record: dict[str, Any], state_keys: set[str]
    ) -> dict[str, Any] | None:
        """Re-prove quarantined steps only if they unlock a plan or save a user input."""

        invocable = load_invocable_capabilities(self.root)
        healthy = {cid: item for cid, item in invocable.items() if not item.get("quarantine")}
        planned = plan_goal_with_elicitation(healthy, state_keys, record["goal"])
        if len(healthy) == len(invocable) or (planned is not None and not planned["elicited_keys"]):
            return planned
        blocked = plan_goal_with_elicitation(invocable, state_keys, record["goal"])
        if blocked is None or (planned is not None and len(blocked["elicited_keys"]) >= len(planned["elicited_keys"])):
            return planned
        attempted = {entry["capability_id"] for entry in record["healing"]}
        entries = heal_quarantined_blockers(
            self.root, invocable, blocked["program"], attempted=attempted
        )
        if entries:
            record["healing"].extend(entries)
            self._transition(record, "healed", {"healing": entries})
        if not any(entry["reinstated"] for entry in entries):
            return planned
        invocable = load_invocable_capabilities(self.root)
        healthy = {cid: item for cid, item in invocable.items() if not item.get("quarantine")}
        healed_plan = plan_goal_with_elicitation(healthy, state_keys, record["goal"])
        if healed_plan is not None and (
            planned is None or len(healed_plan["elicited_keys"]) < len(planned["elicited_keys"])
        ):
            return healed_plan
        return planned

    # -- recovery ---------------------------------------------------------

    @contextmanager
    def _edit(self, session_id: str, recovered: list[str] | None = None) -> Iterator[dict[str, Any]]:
        source = _session_path(self.root, session_id)
        if not durable_read_path(source).is_file():
            raise InvocationError(404, f"unknown session: {session_id}")
        path = durable_write_path(source)
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_guard(path):
            record = self._load(session_id)
            if record.get("status") == "running":
                lease = _try_lease(path.with_suffix(".worker"))
                if lease is not None:
                    with lease:
                        cancel = _CancelRequest(path)
                        detail = "execution owner exited"
                        if cancel.is_set():
                            detail += " before confirming cancellation"
                        record["status"] = "interrupted"
                        self._transition(record, "interrupted", detail)
                        self._persist(record)
                        if recovered is not None:
                            recovered.append(session_id)
            yield record

    def _current(self, session_id: str, recovered: list[str] | None = None) -> dict[str, Any]:
        record = self._load(session_id)
        if record["status"] == "running":
            with self._edit(session_id, recovered) as current:
                return current
        return record

    def _records(self, recovered: list[str] | None = None) -> Iterator[dict[str, Any]]:
        directory = sessions_dir(self.root)
        ids = {p.stem for folder in {directory, durable_read_path(directory)} for p in folder.glob("*.json")}
        for session_id in sorted(ids):
            try:
                yield self._current(session_id, recovered)
            except (InvocationError, OSError, ValueError):
                continue

    def recover(self) -> list[str]:
        """Reconcile abandoned workers and retry pending terminal notifications."""
        recovered: list[str] = []
        for record in self._records(recovered):
            self._maybe_notify(record)
        return recovered

    # -- API --------------------------------------------------------------

    def list_sessions(self) -> dict[str, Any]:
        fields = ("session_id", "status", "goal", "session_digest")
        items = [{key: record.get(key) for key in fields} for record in self._records()]
        return {"ok": True, "sessions": items, "count": len(items)}

    def get_session(self, session_id: str) -> dict[str, Any]:
        record = self._current(session_id)
        return {"ok": True, "session": public_session_record(record)}

    def create_session(
        self,
        initial_state: Any,
        goal: Any,
        *,
        notify_url: Any = None,
        notify_secret: Any = None,
    ) -> dict[str, Any]:
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
        try:
            callback_url, callback_secret = normalize_notify_spec(notify_url, notify_secret)
        except NotifyTargetError as exc:
            raise InvocationError(422, str(exc)) from exc
        goal_keys = list(dict.fromkeys(str(key).strip() for key in goal))
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
            "healing": [],
            "transitions": [],
            "plan_digest": None,
        }
        if callback_url and callback_secret:
            record["notify_url"] = callback_url
            record["notify_secret"] = callback_secret
            record["notify"] = {
                "attempts": 0,
                "delivered": False,
                "last_status": None,
                "last_error": None,
                "delivered_at": None,
            }
        self._transition(record, "created", {"goal": goal_keys})
        path = durable_write_path(_session_path(self.root, session_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_guard(path):
            return self._plan_session(record)

    def supply_input(self, session_id: str, supplied: Any) -> dict[str, Any]:
        with self._edit(session_id) as record:
            if record["status"] != "awaiting_input":
                raise InvocationError(409, f"session {session_id} is {record['status']}, not awaiting input")
            if not isinstance(supplied, dict) or not all(isinstance(key, str) for key in supplied):
                raise InvocationError(422, "input must be a JSON object keyed by state keys")
            pending = set(record["pending_keys"])
            problems = []
            if missing := sorted(pending - supplied.keys()):
                problems.append(f"missing elicited keys: {missing}")
            if extra := sorted(supplied.keys() - pending):
                problems.append(f"unexpected keys: {extra}")
            if problems:
                raise InvocationError(422, "; ".join(problems))
            record["state"].update(supplied)
            record["pending_keys"] = []
            self._transition(record, "input_accepted", {"keys": sorted(supplied)})
            return self._plan_session(record)

    def _plan_session(self, record: dict[str, Any]) -> dict[str, Any]:
        planned = self._plan_with_healing(record, set(record["state"]))
        if planned is None:
            record["status"] = "unsolvable"
            self._transition(record, "unsolvable", "no bounded capability program covers the goal")
            return {"ok": True, "session": public_session_record(self._persist(record))}
        record["plan"] = planned["program"]
        if planned["elicited_keys"]:
            record["elicited_keys"] = sorted(set(record["elicited_keys"]) | set(planned["elicited_keys"]))
            for key, consumer in planned["key_consumers"].items():
                record["key_consumers"].setdefault(key, consumer)
            record["status"] = "awaiting_input"
            record["pending_keys"] = planned["elicited_keys"]
            self._transition(record, "elicited", {"pending_keys": planned["elicited_keys"]})
            return {"ok": True, "session": public_session_record(self._persist(record))}
        self._transition(record, "planned", {"plan": planned["program"]})
        return self._start_execution(record)

    def resume_session(self, session_id: str) -> dict[str, Any]:
        with self._edit(session_id) as record:
            if record["status"] != "interrupted":
                raise InvocationError(409, f"session {session_id} is {record['status']}, not interrupted")
            self._transition(record, "resumed", {"completed_steps": len(record["steps"])})
            return self._start_execution(record)

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        with self._edit(session_id) as record:
            status = record["status"]
            if status in TERMINAL_STATUSES:
                raise InvocationError(409, f"session {session_id} is already {status}")
            if status == "running":
                signal = _CancelRequest(durable_write_path(_session_path(self.root, session_id)))
                signal.path.touch()
                if record["transitions"][-1]["kind"] != "cancel_requested":
                    self._transition(record, "cancel_requested")
            else:
                record["status"] = "cancelled"
                self._transition(record, "cancelled", f"cancelled while {status}")
            return {"ok": True, "session": public_session_record(self._persist(record))}

    # -- outbound notify --------------------------------------------------

    def _maybe_notify(self, record: Mapping[str, Any]) -> None:
        if (
            record["status"] not in TERMINAL_STATUSES or not record.get("notify_url")
            or not record.get("notify_secret") or (record.get("notify") or {}).get("delivered")
        ):
            return
        session_id = record["session_id"]
        path = durable_write_path(_session_path(self.root, session_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        lease = _try_lease(path.with_suffix(".delivery"))
        if lease is not None:
            try:
                threading.Thread(
                    target=self._deliver_notify, args=(session_id, lease), daemon=True, name=f"session-notify-{session_id}"
                ).start()
            except BaseException:
                lease.close()
                raise

    def _deliver_notify(self, session_id: str, lease: ExitStack) -> None:
        try:
            for delay in (0.0, *RETRY_DELAYS_SECONDS):
                if delay:
                    time.sleep(delay)
                record = self._load(session_id)
                if str(record.get("status") or "") not in TERMINAL_STATUSES:
                    return
                if (record.get("notify") or {}).get("delivered"):
                    return
                url = str(record.get("notify_url") or "")
                secret = str(record.get("notify_secret") or "")
                if not url or not secret:
                    return
                status, error = deliver_session_notify(url, secret, record)
                notify = dict(record.get("notify") or {})
                notify["attempts"] = int(notify.get("attempts") or 0) + 1
                notify["last_status"] = status
                notify["last_error"] = error or None
                if 200 <= status < 300:
                    notify["delivered"] = True
                    notify["delivered_at"] = utc_now_iso()
                record["notify"] = notify
                self._persist(record, notify=False)
                if not should_retry_notify(status, error):
                    return
        except Exception:
            return
        finally:
            lease.close()

    # -- execution --------------------------------------------------------

    def _start_execution(self, record: dict[str, Any]) -> dict[str, Any]:
        # The caller holds the record lock. Publish running only after acquiring
        # the worker lease, then transfer its handle to the execution thread.
        session_id = record["session_id"]
        path = durable_write_path(_session_path(self.root, session_id))
        lease = _try_lease(path.with_suffix(".worker"))
        if lease is None:
            raise InvocationError(409, f"session {session_id} already has an execution owner")
        try:
            _CancelRequest(path).path.unlink(missing_ok=True)
            record["status"] = "running"
            self._persist(record)
            threading.Thread(
                target=self._execute, args=(session_id, path, lease), daemon=True, name=f"session-{session_id}"
            ).start()
        except BaseException:
            lease.close()
            raise
        return {"ok": True, "session": public_session_record(record)}

    def _execute(self, session_id: str, path: Path, lease: ExitStack) -> None:
        cancel_event = _CancelRequest(path)

        def checkpoint() -> None:
            with file_guard(path):
                if cancel_event.is_set():
                    raise ProcessCancelled()
                self._persist(record)

        try:
            record = self._load(session_id)
            invocable = load_invocable_capabilities(self.root)
            state = dict(record["state"])
            program = list(record["plan"] or [])
            for capability_id in program[len(record["steps"]):]:
                if cancel_event.is_set():
                    raise ProcessCancelled()
                item = invocable.get(capability_id)
                if item is None:
                    raise InvocationError(502, f"planned capability is no longer invocable: {capability_id}")
                step_input = {key: state[key] for key in item["requires"]}
                try:
                    result = invoke_capability(
                        self.root, capability_id, step_input, cancel_event=cancel_event
                    )
                except InvocationError as exc:
                    # Quarantined between planning and execution (a concurrent
                    # violation, or one attributed to this step): heal once
                    # under supervised re-proof and retry, like /solve does.
                    violation = (exc.extra or {}).get("violation")
                    attempted = {entry["capability_id"] for entry in record["healing"]}
                    if (
                        violation not in {"resource_quarantined", "resource_limit"}
                        or capability_id in attempted
                        or len(attempted) >= SOLVE_MAX_HEALED
                    ):
                        raise
                    # The quarantine was recorded after this session's
                    # planning snapshot; reload so the healer can see it.
                    invocable = load_invocable_capabilities(self.root)
                    entries = heal_quarantined_blockers(
                        self.root, invocable, [capability_id], attempted=attempted
                    )
                    record["healing"].extend(entries)
                    self._transition(record, "healed", {"healing": entries})
                    checkpoint()
                    if not entries or not entries[-1]["reinstated"]:
                        raise
                    invocable = load_invocable_capabilities(self.root)
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
                checkpoint()
            outcome = {key: state[key] for key in record["goal"]}
            record["outcome"] = outcome
            record["status"] = "solved"
            record["plan_digest"] = _plan_digest(record)
            self._transition(record, "solved", {"plan_digest": record["plan_digest"]})
            checkpoint()
        except Exception as exc:
            with file_guard(path):
                record = self._load(session_id)
                if isinstance(exc, ProcessCancelled) or cancel_event.is_set():
                    record["status"] = "cancelled"
                    self._transition(record, "cancelled", "worker stopped by cancel request")
                else:
                    record["status"] = "failed"
                    record["error"] = exc.error if isinstance(exc, InvocationError) else f"{type(exc).__name__}: {exc}"
                    self._transition(record, "failed", {"error": record["error"]})
                self._persist(record)
                cancel_event.path.unlink(missing_ok=True)
        finally:
            lease.close()
