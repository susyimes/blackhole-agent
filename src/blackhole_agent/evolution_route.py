"""Evolution surface routing: prefer Capability Compounder over skill-route cascades.

When a durable capability ledger is ready, growth should compound through
register/prove/run/compose instead of nesting skill_route pin/cascade paperwork.
This module is the single decision point for that redirect.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    default_ledger_path,
    load_ledger,
    topological_order,
)

COMPOUND_SURFACE = "capability_compounder"
LEGACY_GROWTH_SURFACE = "legacy_github_growth"
REDIRECT_CONTROLLER_SURFACE = "capability_compounder_redirect"
ENV_PREFER_COMPOUNDER = "BLACKHOLE_PREFER_CAPABILITY_COMPOUNDER"
ENV_FORCE_SKILL_ROUTE = "BLACKHOLE_FORCE_SKILL_ROUTE_PIPELINE"
DEFAULT_COMPOSE_IDS = (
    "repo.import-health",
    "unbound.milestone-gate",
    "capability.ledger-inventory",
)


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def ledger_compound_ready(
    repo_path: Path,
    *,
    min_count: int = 2,
) -> dict[str, Any]:
    """Inspect the durable ledger and report whether compound growth is available."""

    path = default_ledger_path(repo_path)
    if not path.exists():
        return {
            "ready": False,
            "ledger_path": str(path),
            "count": 0,
            "proved_count": 0,
            "ids": [],
            "reason": "ledger_missing",
        }
    try:
        ledger = load_ledger(path)
    except (OSError, ValueError, TypeError) as error:
        return {
            "ready": False,
            "ledger_path": str(path),
            "count": 0,
            "proved_count": 0,
            "ids": [],
            "reason": f"ledger_unreadable:{error}",
        }
    ids = sorted(ledger.capabilities)
    proved = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if capability.last_proof_exit_code == 0
    ]
    ready = len(ids) >= min_count
    return {
        "ready": ready,
        "ledger_path": str(path),
        "count": len(ids),
        "proved_count": len(proved),
        "ids": ids,
        "proved_ids": sorted(proved),
        "reason": "ready" if ready else "insufficient_capabilities",
    }


def should_redirect_skill_route_pipeline(
    repo_path: Path | None = None,
    *,
    prefer_capability_compounder: bool | None = None,
    min_count: int = 2,
) -> bool:
    """Return True when skill-route cascade packaging should yield to the compounder."""

    force_skill = _env_flag(ENV_FORCE_SKILL_ROUTE)
    if force_skill is True:
        return False
    prefer = prefer_capability_compounder
    if prefer is None:
        env_prefer = _env_flag(ENV_PREFER_COMPOUNDER)
        if env_prefer is not None:
            prefer = env_prefer
        else:
            prefer = True  # compounder-first once a ledger exists
    if not prefer:
        return False
    root = (repo_path or Path.cwd()).resolve()
    return bool(ledger_compound_ready(root, min_count=min_count)["ready"])


def build_skill_route_compounder_redirect_pipeline(
    *,
    proposals: Sequence[Mapping[str, Any]] | None = None,
    theme_window: Mapping[str, Any] | None = None,
    source_digest: str | None = None,
    repo_path: Path | None = None,
    ledger_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact pipeline that freezes pin/cascade stages and points at the compounder.

    This intentionally omits residual adjacent handoff/acceptance cascade stages
    that previously nested continue_cascade / pin_call_next paperwork.
    """

    root = (repo_path or Path.cwd()).resolve()
    status = dict(ledger_status or ledger_compound_ready(root))
    proposal_ids = [
        str(item.get("proposal_id") or "").strip()
        for item in (proposals or [])
        if str(item.get("proposal_id") or "").strip()
    ]
    theme = dict(theme_window or {})
    compose_ids = [item for item in DEFAULT_COMPOSE_IDS if item in set(status.get("ids") or [])]
    if not compose_ids:
        compose_ids = list(status.get("ids") or [])[:3]
    return {
        "schema_version": 1,
        "controller_surface": REDIRECT_CONTROLLER_SURFACE,
        "evolution_surface": COMPOUND_SURFACE,
        "policy": "prefer_capability_compounder_over_skill_route_pin_cascade",
        "status": "redirected_to_capability_compounder",
        "theme_id": str(theme.get("theme_id") or "capability-compounder"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or 0),
            "status": "redirected",
        },
        "pipeline_stages": [
            "ledger_ready_check",
            "freeze_skill_route_pin_cascade",
            "capability_compounder_compose",
        ],
        "skill_route_pin_cascade_frozen": True,
        "skill_route_nested_stages_omitted": [
            "continue_cascade_wake_route_apply_follow_pin",
            "pin_call_next_call_follow",
            "residual_adjacent_focused_validation_activation_external_acceptance",
        ],
        "classifier": {
            "status": "bypassed_for_compounder_redirect",
            "candidate_count": len(proposal_ids),
            "proposal_ids_noted": proposal_ids[:12],
        },
        "selected_step": {
            "proposal_id": "cap-compounder-redirect",
            "route_class": "capability_compounder",
            "status": "ready",
            "selection_reason": (
                "Durable capability ledger is ready; prefer prove/compose over "
                "skill_route_discovery pin/cascade packaging."
            ),
            "runtime_action": "run_capability_compounder",
            "allowed_local_lanes": ["code_patch", "test", "documentation", "config"],
        },
        "capability_compounder": {
            "status": "ready" if status.get("ready") else "not_ready",
            "ledger_path": status.get("ledger_path"),
            "capability_count": status.get("count"),
            "proved_count": status.get("proved_count"),
            "capability_ids": status.get("ids") or [],
            "compose_ids": compose_ids,
            "cli": {
                "demo": "blackhole-unbound capability demo",
                "compose": "blackhole-unbound capability compose "
                + ",".join(compose_ids or DEFAULT_COMPOSE_IDS),
                "list": "blackhole-unbound capability list",
            },
        },
        "supervisor_next_action": "run_capability_compounder_compose_or_demo",
        "supervisor_next": "run_capability_compounder_compose_or_demo",
        "source_digest": source_digest or "",
        "runtime_action": "none_external",
        "denied": [
            "external_skill_execution",
            "provider_launch",
            "remote_apply",
            "skill_route_pin_cascade_expansion",
        ],
    }


def resolve_supervisor_evolution_surface(
    *,
    evolution_mode: str,
    repo_path: Path,
    prefer_capability_compounder: bool = True,
) -> dict[str, Any]:
    """Decide which wake surface the supervisor should launch."""

    mode = (evolution_mode or "").strip().lower()
    ledger = ledger_compound_ready(repo_path)
    force_skill = _env_flag(ENV_FORCE_SKILL_ROUTE) is True
    env_prefer = _env_flag(ENV_PREFER_COMPOUNDER)
    prefer = prefer_capability_compounder if env_prefer is None else env_prefer

    if mode == "compound":
        return {
            "surface": COMPOUND_SURFACE,
            "effective_mode": "compound",
            "redirected": mode != "compound",
            "reason": "explicit_compound_mode",
            "ledger": ledger,
        }
    if mode in {"digest", "plan"}:
        return {
            "surface": LEGACY_GROWTH_SURFACE,
            "effective_mode": mode,
            "redirected": False,
            "reason": f"non_mutation_mode_{mode}",
            "ledger": ledger,
        }
    if mode == "codex" and prefer and not force_skill and ledger.get("ready"):
        return {
            "surface": COMPOUND_SURFACE,
            "effective_mode": "compound",
            "redirected": True,
            "reason": "prefer_capability_compounder_ledger_ready",
            "ledger": ledger,
        }
    return {
        "surface": LEGACY_GROWTH_SURFACE,
        "effective_mode": mode or "codex",
        "redirected": False,
        "reason": "legacy_github_growth",
        "ledger": ledger,
    }


def build_compound_wake_command(
    *,
    repo_path: Path,
    capability_ids: Sequence[str] | None = None,
    use_demo: bool = True,
) -> list[str]:
    """One-shot child command that compounds capabilities instead of skill-route evolution."""

    root = str(repo_path.resolve())
    if use_demo:
        return [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "demo",
            "--repo-path",
            root,
        ]
    ids = list(capability_ids or DEFAULT_COMPOSE_IDS)
    return [
        sys.executable,
        "-m",
        "blackhole_agent.unbound",
        "capability",
        "compose",
        ",".join(ids),
        "--repo-path",
        root,
    ]


def select_compose_ids(repo_path: Path, requested: Sequence[str] | None = None) -> list[str]:
    status = ledger_compound_ready(repo_path, min_count=1)
    available = set(status.get("ids") or [])
    if requested:
        chosen = [item for item in requested if item in available]
        if chosen:
            return chosen
    default = [item for item in DEFAULT_COMPOSE_IDS if item in available]
    if default:
        try:
            ledger = load_ledger(default_ledger_path(repo_path))
            return topological_order(ledger, default)
        except Exception:
            return default
    return sorted(available)[:3]
