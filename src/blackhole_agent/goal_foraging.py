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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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
    return {
        "candidate": str(candidate.get("name")),
        "slug": str(result.get("slug") or candidate.get("slug") or ""),
        "ok": bool(result.get("ok")),
        "stage": result.get("stage"),
        "capability_id": result.get("capability_id"),
        "error": result.get("error"),
    }


def solve_with_forage(
    root: Path,
    initial_state: Any,
    goal: Any,
    candidates: Any = None,
    *,
    timeout: int = 120,
    max_steps: int = 8,
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

    first = solve_goal_request(root, initial_state, goal_keys, timeout=timeout, max_steps=max_steps)
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
            result = forage_package(candidate, repo_root=root, scenario=False)
            attempts.append(_attempt_record(candidate, result))
            if not result.get("ok"):
                continue
            capability_id = str(result.get("capability_id") or "")
            if capability_id:
                acquired.append(capability_id)
            retry = solve_goal_request(
                root, initial_state, goal_keys, timeout=timeout, max_steps=max_steps
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

    verdict = solve_goal_request(root, initial_state, goal_keys, timeout=timeout, max_steps=max_steps)
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
