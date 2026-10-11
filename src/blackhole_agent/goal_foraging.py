"""Goal-driven foraging: unsolvable goals autonomously acquire what they need.

The foraging plane turns a bare package source into proved ledger
capabilities, but only when an operator runs it by hand; the goal solver
honestly reports ``solved: false`` when no proved capability program covers
the goal and stops. This module closes the two into one loop:

1. **plan first** — the declarative goal is attempted over the live proved
   ledger exactly as the solver does; an already-solvable goal is answered
   without acquiring anything;
2. **forage on miss** — when no program exists, each operator-named forage
   candidate (a bare local source, or a registry name) is foraged zero-spec:
   the spec is inferred, the tool is absorbed, proved, and registered in the
   workspace ledger. After every successful acquisition the goal is
   re-planned and re-executed for real;
3. **honest bounds** — the first candidate whose acquisition makes the goal
   solvable wins; candidates that fail to forage or fail to cover the goal
   are recorded as attempts and the loop moves on. When no candidate closes
   the gap the verdict stays ``solved: false`` with the still-uncovered goal
   keys named, and malformed requests are refused before anything is
   acquired. Acquisitions are real and durable: a capability foraged during
   an unsuccessful loop remains proved in the ledger.

The CLI (``python -m blackhole_agent.goal_foraging solve ...``) is the
operator surface: one command goes from an unsolvable goal to an executed,
digest-bound outcome.

The live invocation plane exposes the same loop on ``POST /solve`` when the
operator opts in with ``--forage-root`` (or ``BLACKHOLE_FORAGE_ROOT``).
HTTP forage names are resolved as subpaths of that root: registry fetches
and paths that escape the root are refused. A plane without a forage root
stays fail-closed (``solve_forage: false``); extra ``forage`` on the body
is ``400 forage_disabled``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_absorption import REPO_ROOT_ENV
from blackhole_agent.capability_foraging import forage_package
from blackhole_agent.capability_service import (
    InvocationError,
    load_invocable_capabilities,
    solve_goal_request,
)

SCHEMA_VERSION = 1
MAX_FORAGE_CANDIDATES = 8
FORAGE_ROOT_ENV = "BLACKHOLE_FORAGE_ROOT"

_forage_root_lock = threading.Lock()
_configured_forage_root: Path | None = None


class ForageRootError(ValueError):
    """Raised when ``--forage-root`` is set but cannot be used as a source tree."""

    def __init__(self, error: str, **extra: Any) -> None:
        self.error = str(error)
        self.payload = {"ok": False, "error": self.error, **extra}
        super().__init__(self.error)


def resolve_forage_root(raw: str | Path | None = None, *, env: Mapping[str, str] | None = None) -> Path | None:
    """Return the operator forage root from a CLI value or ``BLACKHOLE_FORAGE_ROOT``."""

    text = str(raw or "").strip()
    if not text:
        source = env if env is not None else os.environ
        text = str(source.get(FORAGE_ROOT_ENV) or "").strip()
    if not text:
        return None
    return Path(text)


def configure_forage_root(root: str | Path | None) -> Path | None:
    """Pin the live-plane forage root, or clear it so HTTP forage stays disabled."""

    global _configured_forage_root
    if root is None or str(root).strip() == "":
        with _forage_root_lock:
            _configured_forage_root = None
        return None
    path = Path(root).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ForageRootError("forage_root_unreadable", path=str(path), detail=str(exc)) from exc
    if not resolved.exists():
        raise ForageRootError("forage_root_unreadable", path=str(resolved))
    if not resolved.is_dir():
        raise ForageRootError("forage_root_not_directory", path=str(resolved))
    with _forage_root_lock:
        _configured_forage_root = resolved
    return resolved


def current_forage_root() -> Path | None:
    with _forage_root_lock:
        return _configured_forage_root


def forage_health() -> dict[str, Any]:
    """Health fragment: forage-on-solve is advertised only when a root is pinned."""

    return {"solve_forage": current_forage_root() is not None}


def _relative_forage_name(raw: str) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        raise InvocationError(400, "forage_path_not_allowed")
    first = text.split("/", 1)[0]
    if ":" in first:
        raise InvocationError(400, "forage_path_not_allowed")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise InvocationError(400, "forage_path_not_allowed")
    return "/".join(parts)


def resolve_live_forage_candidates(raw: Any) -> list[dict[str, Any]]:
    """Map HTTP ``forage`` names onto directories under the pinned forage root.

    Registry fetches and absolute/escaping paths are refused. Each name is a
    relative directory under the root; optional object fields ``slug`` and
    ``hint`` are forwarded to the foraging plane.
    """

    root = current_forage_root()
    if root is None:
        raise InvocationError(400, "forage_disabled")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InvocationError(422, "forage must be a list of names or forage objects")
    if len(raw) > MAX_FORAGE_CANDIDATES:
        raise InvocationError(422, f"at most {MAX_FORAGE_CANDIDATES} forage candidates per request")
    resolved_root = root.resolve()
    validated: list[dict[str, Any]] = []
    for item in raw:
        hint = ""
        slug = ""
        if isinstance(item, str):
            name = _relative_forage_name(item)
        elif isinstance(item, dict):
            if item.get("source") is not None or item.get("registry") is not None:
                raise InvocationError(400, "forage_path_not_allowed")
            name = _relative_forage_name(str(item.get("name") or ""))
            if item.get("slug") is not None:
                slug = str(item.get("slug") or "").strip()
            if item.get("hint") is not None:
                hint = str(item.get("hint") or "").strip()
        else:
            raise InvocationError(422, "each forage entry must be a name or object")
        leaf = name.rsplit("/", 1)[-1]
        source = (resolved_root / Path(*name.split("/"))).resolve()
        try:
            source.relative_to(resolved_root)
        except ValueError as exc:
            raise InvocationError(400, "forage_path_not_allowed") from exc
        if not source.is_dir():
            raise InvocationError(400, "forage_source_missing")
        validated.append(
            {
                "name": name,
                "slug": slug or leaf,
                "hint": hint or leaf.replace("-", "_"),
                "source": str(source),
                "origin": {"kind": "live-forage", "source": name},
            }
        )
    return validated


def uncovered_goal_keys(
    invocable: Mapping[str, Mapping[str, Any]],
    initial_keys: set[str],
    goal_keys: Sequence[str],
) -> list[str]:
    """Goal keys no proved-capability closure can provide.

    The monotone closure of ``provides`` over applicable capabilities is the
    largest reachable key set; goal keys outside it are exactly what
    acquisition must supply.
    """

    available = set(initial_keys)
    changed = True
    while changed:
        changed = False
        for item in invocable.values():
            provides = set(item["provides"])
            if set(item["requires"]) <= available and not provides <= available:
                available |= provides
                changed = True
    return sorted(set(goal_keys) - available)


def _validated_goal_request(initial_state: Any, goal: Any) -> list[str]:
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
    return list(dict.fromkeys(str(key).strip() for key in goal))


def _validated_candidates(candidates: Any) -> list[dict[str, Any]]:
    if candidates is None:
        return []
    if not isinstance(candidates, list):
        raise InvocationError(422, "candidates must be a list of forage request objects")
    if len(candidates) > MAX_FORAGE_CANDIDATES:
        raise InvocationError(422, f"at most {MAX_FORAGE_CANDIDATES} forage candidates per request")
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise InvocationError(422, "each candidate must be a forage request object")
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvocationError(422, "each candidate needs a non-empty 'name'")
        source = candidate.get("source")
        registry = candidate.get("registry")
        if source is None and not (isinstance(registry, str) and registry.strip()):
            raise InvocationError(
                422, f"candidate '{name}' needs a 'source' path or a 'registry'"
            )
        validated.append(dict(candidate))
    return validated


def _attempt_record(candidate: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "candidate": str(candidate.get("name")),
        "slug": str(result.get("slug") or candidate.get("slug") or ""),
        "ok": bool(result.get("ok")),
        "stage": result.get("stage"),
        "capability_id": result.get("capability_id"),
        "error": result.get("error"),
    }
    if result.get("proof_summary"):
        record["proof_summary"] = result.get("proof_summary")
    return record


def solve_with_forage(
    root: Path,
    initial_state: Any,
    goal: Any,
    candidates: Any = None,
    *,
    timeout: int = 120,
    max_steps: int = 8,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Solve a declarative goal, foraging named candidates when unplannable.

    Planning and execution are exactly the goal solver's; acquisition is the
    foraging plane's, scoped to ``root`` (vendored trees, persisted records,
    and the ledger proof subprocess all resolve under it). Returns the
    solver's verdict extended with an ``acquisition`` record of every forage
    attempt; nothing is fabricated — a goal no candidate can cover is
    reported unsolved with the uncovered keys named.
    """

    goal_keys = _validated_goal_request(initial_state, goal)
    forage_requests = _validated_candidates(candidates)
    root = Path(root).resolve()

    first = solve_goal_request(
        root,
        initial_state,
        goal_keys,
        timeout=timeout,
        max_steps=max_steps,
        cancel_event=cancel_event,
    )
    if first.get("solved"):
        first["acquisition"] = {
            "needed": False,
            "foraged": [],
            "acquired_capability_ids": [],
        }
        return first
    if not forage_requests:
        first["uncovered"] = uncovered_goal_keys(
            load_invocable_capabilities(root), set(initial_state), goal_keys
        )
        first["acquisition"] = {
            "needed": True,
            "foraged": [],
            "acquired_capability_ids": [],
        }
        return first

    attempts: list[dict[str, Any]] = []
    acquired: list[str] = []
    previous_env = os.environ.get(REPO_ROOT_ENV)
    os.environ[REPO_ROOT_ENV] = str(root)
    try:
        for candidate in forage_requests:
            if cancel_event is not None and cancel_event.is_set():
                from blackhole_agent.process_capture import ProcessCancelled

                raise ProcessCancelled("forage cancelled")
            result = forage_package(candidate, repo_root=root, scenario=False)
            attempts.append(_attempt_record(candidate, result))
            if not result.get("ok"):
                continue
            capability_id = str(result.get("capability_id") or "")
            if capability_id:
                acquired.append(capability_id)
            retry = solve_goal_request(
                root,
                initial_state,
                goal_keys,
                timeout=timeout,
                max_steps=max_steps,
                cancel_event=cancel_event,
            )
            if retry.get("solved"):
                retry["acquisition"] = {
                    "needed": True,
                    "foraged": attempts,
                    "acquired_capability_ids": acquired,
                }
                return retry
    finally:
        if previous_env is None:
            os.environ.pop(REPO_ROOT_ENV, None)
        else:
            os.environ[REPO_ROOT_ENV] = previous_env

    verdict = solve_goal_request(
        root,
        initial_state,
        goal_keys,
        timeout=timeout,
        max_steps=max_steps,
        cancel_event=cancel_event,
    )
    verdict["uncovered"] = uncovered_goal_keys(
        load_invocable_capabilities(root), set(initial_state), goal_keys
    )
    verdict["reason"] = "no forage candidate closed the goal"
    verdict["acquisition"] = {
        "needed": True,
        "foraged": attempts,
        "acquired_capability_ids": acquired,
    }
    return verdict


def _parse_candidate(text: str) -> dict[str, Any]:
    try:
        candidate = json.loads(text)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"candidate is not valid JSON: {exc}") from exc
    if not isinstance(candidate, dict):
        raise argparse.ArgumentTypeError("candidate must be a JSON object")
    return candidate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="goal_foraging",
        description="Solve a declarative goal, foraging package candidates on a miss.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    solve = subparsers.add_parser("solve", help="solve a goal, foraging candidates if unplannable")
    solve.add_argument("--root", required=True, help="workspace root holding capabilities/")
    solve.add_argument("--state", required=True, help="initial state as a JSON object")
    solve.add_argument("--goal", required=True, help="comma-separated goal state keys")
    solve.add_argument(
        "--candidate",
        action="append",
        type=_parse_candidate,
        default=[],
        help="forage request as a JSON object; repeatable",
    )
    args = parser.parse_args(argv)

    try:
        initial_state = json.loads(args.state)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"--state is not valid JSON: {exc}"}))
        return 2
    goal = [key.strip() for key in args.goal.split(",") if key.strip()]
    try:
        verdict = solve_with_forage(
            Path(args.root), initial_state, goal, list(args.candidate)
        )
    except InvocationError as exc:
        print(json.dumps({"ok": False, "error": exc.error}))
        return 2
    verdict["schema_version"] = SCHEMA_VERSION
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
