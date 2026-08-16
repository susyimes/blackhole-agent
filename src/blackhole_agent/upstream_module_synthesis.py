"""Module-synthesis plane: one finder owns facade, pair-effect, and log-family modules.

The three leftover meta-path finders were copies of the same resolve →
bootstrap → ``get_code`` contract. They now share one catalog and one
finder. A synthesized module is a :class:`ModuleSynthesisRow`; historical
``install_facade_finder`` / ``install_pair_effect_finder`` /
``install_log_family_finder`` names stay as thin wrappers.

Facade bootstrap stays in the host registry. Pair-effect and log-family
populate through :mod:`blackhole_agent.upstream_spine_family` so a new
family is a catalog row, not another host synthesizer copy. Historical
``python -m`` shims keep their import paths.

No skill-route discovery.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]

MODULE_SYNTHESIS_IMPL = True
_FACADE_PREFIX = "blackhole_agent.upstream_"
_SPINE_PREFIX = "blackhole_agent.upstream_total_spine_"


@dataclass(frozen=True)
class ModuleSynthesisRow:
    """One synthesized import path."""

    kind: str  # facade | pair_effect | log_family
    name: str
    fullname: str
    origin: str
    filename: str
    shim: str


_LIVE_CATALOG: tuple[ModuleSynthesisRow, ...] | None = None
_LIVE_INDEX: dict[str, ModuleSynthesisRow] | None = None


def _facade_row(name: str) -> ModuleSynthesisRow:
    return ModuleSynthesisRow(
        kind="facade",
        name=name,
        fullname=f"{_FACADE_PREFIX}{name}",
        origin=f"<upstream-layer:{name}>",
        filename=f"<upstream-layer {name}>",
        shim=(
            "from __future__ import annotations\n"
            "import sys\n"
            "from blackhole_agent.upstream_layer_registry import bootstrap_layer\n"
            f"bootstrap_layer(globals(), {name!r})\n"
        ),
    )


def _pair_row(name: str) -> ModuleSynthesisRow:
    return ModuleSynthesisRow(
        kind="pair_effect",
        name=name,
        fullname=f"{_SPINE_PREFIX}{name}",
        origin=f"<upstream-total-spine-effect:{name}>",
        filename=f"<upstream-total-spine-effect {name}>",
        shim=(
            "from blackhole_agent.upstream_total_spine_effects import "
            "_effect_main_from_module\n"
            f"_effect_main_from_module({name!r}, globals())\n"
        ),
    )


def _log_row(name: str) -> ModuleSynthesisRow:
    return ModuleSynthesisRow(
        kind="log_family",
        name=name,
        fullname=f"{_SPINE_PREFIX}{name}",
        origin=f"<upstream-total-spine-log:{name}>",
        filename=f"<upstream-total-spine-log {name}>",
        shim=(
            "from blackhole_agent.upstream_total_spine_logs import "
            "_log_main_from_module\n"
            f"_log_main_from_module({name!r}, globals())\n"
        ),
    )


def derive_module_synthesis_catalog(
    *,
    extra_facade: Sequence[str] = (),
    extra_pair: Sequence[str] = (),
    extra_log: Sequence[str] = (),
    facade_layers: Sequence[str] | None = None,
    pair_families: Sequence[str] | None = None,
    log_families: Sequence[str] | None = None,
) -> tuple[ModuleSynthesisRow, ...]:
    """Build the synthesis catalog from host registries plus optional probes."""

    if facade_layers is None:
        from blackhole_agent.upstream_layer_registry import FACADE_LAYERS

        facade_layers = FACADE_LAYERS
    if pair_families is None:
        from blackhole_agent.upstream_total_spine_effects import PAIR_EFFECT_SPECS

        pair_families = tuple(PAIR_EFFECT_SPECS)
    if log_families is None:
        from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

        log_families = tuple(LOG_FAMILY_SPECS)
    rows = [_facade_row(name) for name in list(facade_layers) + list(extra_facade)]
    rows.extend(_pair_row(name) for name in list(pair_families) + list(extra_pair))
    rows.extend(_log_row(name) for name in list(log_families) + list(extra_log))
    return tuple(rows)


def module_synthesis_catalog() -> tuple[ModuleSynthesisRow, ...]:
    """Live catalog (cached). A probe extra does not mutate this."""

    global _LIVE_CATALOG, _LIVE_INDEX
    if _LIVE_CATALOG is None:
        _LIVE_CATALOG = derive_module_synthesis_catalog()
        _LIVE_INDEX = {row.fullname: row for row in _LIVE_CATALOG}
    return _LIVE_CATALOG


def resolve_synthesis_row(
    fullname: str,
    catalog: Sequence[ModuleSynthesisRow] | None = None,
) -> ModuleSynthesisRow | None:
    """Resolve one import path against the live catalog or a probe catalog."""

    if catalog is None:
        module_synthesis_catalog()
        return (_LIVE_INDEX or {}).get(fullname)
    for row in catalog:
        if row.fullname == fullname:
            return row
    return None


def _exec_row(row: ModuleSynthesisRow, module: Any) -> None:
    if row.kind == "facade":
        exec(compile(row.shim, row.filename, "exec"), module.__dict__)
        return
    from blackhole_agent.upstream_spine_family import populate_family_module

    populate_family_module(row, module)


class _ModuleSynthesisLoader(Loader):
    """Loads one catalog row; ``get_code`` keeps ``python -m`` working."""

    def __init__(self, row: ModuleSynthesisRow) -> None:
        self._row = row

    def create_module(self, spec: ModuleSpec) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        _exec_row(self._row, module)

    def get_code(self, fullname: str) -> Any:
        return compile(self._row.shim, self._row.filename, "exec")


class _ModuleSynthesisFinder(MetaPathFinder):
    """Resolves every synthesized facade / pair-effect / log-family module."""

    def find_spec(
        self, fullname: str, path: Any = None, target: Any = None
    ) -> ModuleSpec | None:
        row = resolve_synthesis_row(fullname)
        if row is None:
            return None
        return ModuleSpec(
            fullname,
            _ModuleSynthesisLoader(row),
            origin=row.origin,
            is_package=False,
        )


def install_module_synthesis_finder() -> None:
    """Idempotently install the shared synthesis finder."""

    if not any(
        isinstance(finder, _ModuleSynthesisFinder) for finder in sys.meta_path
    ):
        sys.meta_path.append(_ModuleSynthesisFinder())


def leftover_finder_types() -> tuple[type, ...]:
    """Historical finder classes, if any leftover copies are still imported."""

    found: list[type] = []
    for module_name, attr in (
        ("blackhole_agent.upstream_layer_registry", "_FacadeFinder"),
        ("blackhole_agent.upstream_total_spine_effects", "_PairEffectFinder"),
        ("blackhole_agent.upstream_total_spine_logs", "_LogFamilyFinder"),
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        cls = getattr(module, attr, None)
        if isinstance(cls, type):
            found.append(cls)
    return tuple(found)


def builtin_module_synthesis_plane_proof() -> dict[str, Any]:
    """Hermetic proof: leftover finders are one synthesis catalog."""

    import importlib
    import importlib.util
    import inspect

    checks: dict[str, bool] = {}
    catalog = module_synthesis_catalog()
    kinds: dict[str, int] = {"facade": 0, "pair_effect": 0, "log_family": 0}
    for row in catalog:
        kinds[row.kind] = kinds.get(row.kind, 0) + 1
    from blackhole_agent.upstream_layer_registry import FACADE_LAYERS
    from blackhole_agent.upstream_total_spine_effects import PAIR_EFFECT_SPECS
    from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

    checks["impl"] = MODULE_SYNTHESIS_IMPL is True
    checks["facade_count"] = kinds["facade"] == len(FACADE_LAYERS)
    checks["pair_count"] = kinds["pair_effect"] == len(PAIR_EFFECT_SPECS)
    checks["log_count"] = kinds["log_family"] == len(LOG_FAMILY_SPECS)
    checks["catalog_len"] = len(catalog) == (
        kinds["facade"] + kinds["pair_effect"] + kinds["log_family"]
    )
    fullnames = [row.fullname for row in catalog]
    checks["unique_fullnames"] = len(fullnames) == len(set(fullnames))
    checks["resolve_omniverse"] = (
        resolve_synthesis_row("blackhole_agent.upstream_omniverse") is not None
        and resolve_synthesis_row("blackhole_agent.upstream_omniverse").kind
        == "facade"
    )
    checks["resolve_solvency"] = (
        resolve_synthesis_row("blackhole_agent.upstream_total_spine_solvency")
        is not None
        and resolve_synthesis_row(
            "blackhole_agent.upstream_total_spine_solvency"
        ).kind
        == "pair_effect"
    )
    checks["resolve_actuation"] = (
        resolve_synthesis_row("blackhole_agent.upstream_total_spine_actuation")
        is not None
        and resolve_synthesis_row(
            "blackhole_agent.upstream_total_spine_actuation"
        ).kind
        == "log_family"
    )
    checks["unknown_refused"] = (
        resolve_synthesis_row("blackhole_agent.upstream_not_a_layer") is None
    )

    install_module_synthesis_finder()
    unified = [
        finder
        for finder in sys.meta_path
        if isinstance(finder, _ModuleSynthesisFinder)
    ]
    leftover_live = [
        finder
        for finder in sys.meta_path
        if type(finder).__name__
        in {"_FacadeFinder", "_PairEffectFinder", "_LogFamilyFinder"}
    ]
    checks["one_finder"] = len(unified) == 1
    checks["no_leftover_finders"] = leftover_live == []

    omniverse = importlib.import_module("blackhole_agent.upstream_omniverse")
    solvency = importlib.import_module("blackhole_agent.upstream_total_spine_solvency")
    actuation = importlib.import_module("blackhole_agent.upstream_total_spine_actuation")
    checks["no_leftover_types"] = leftover_finder_types() == ()
    checks["omniverse_main"] = callable(getattr(omniverse, "main", None))
    checks["solvency_runner"] = callable(
        getattr(solvency, "solvency_total_spine", None)
    )
    checks["actuation_runner"] = callable(
        getattr(actuation, "actuate_total_spine", None)
    )
    spec = importlib.util.find_spec("blackhole_agent.upstream_omniverse")
    checks["find_spec"] = spec is not None and spec.origin == (
        "<upstream-layer:omniverse>"
    )
    checks["get_code"] = spec is not None and spec.loader is not None and (
        spec.loader.get_code("blackhole_agent.upstream_omniverse") is not None
    )

    probe = derive_module_synthesis_catalog(extra_pair=("supervision",))
    probe_row = resolve_synthesis_row(
        "blackhole_agent.upstream_total_spine_supervision",
        catalog=probe,
    )
    checks["probe_row"] = (
        probe_row is not None and probe_row.kind == "pair_effect"
    )
    checks["probe_not_live"] = (
        resolve_synthesis_row(
            "blackhole_agent.upstream_total_spine_supervision"
        )
        is None
    )
    checks["probe_len"] = len(probe) == len(catalog) + 1

    init_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "__init__.py"
    ).read_text(encoding="utf-8")
    checks["init_installs_plane"] = "install_module_synthesis_finder" in init_src
    checks["init_no_triple_install"] = (
        "install_pair_effect_finder" not in init_src
        and "install_log_family_finder" not in init_src
        and "install_facade_finder" not in init_src
    )
    registry_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_layer_registry.py"
    ).read_text(encoding="utf-8")
    effects_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_total_spine_effects.py"
    ).read_text(encoding="utf-8")
    logs_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_total_spine_logs.py"
    ).read_text(encoding="utf-8")
    checks["no_facade_finder_class"] = "class _FacadeFinder" not in registry_src
    checks["no_pair_finder_class"] = "class _PairEffectFinder" not in effects_src
    checks["no_log_finder_class"] = "class _LogFamilyFinder" not in logs_src
    checks["wrappers_delegate"] = (
        "install_module_synthesis_finder" in registry_src
        and "install_module_synthesis_finder" in effects_src
        and "install_module_synthesis_finder" in logs_src
    )
    checks["bootstrap_stays"] = "def bootstrap_layer" in registry_src
    checks["pair_main_stays"] = "def _effect_main_from_module" in effects_src
    checks["log_main_stays"] = "def _log_main_from_module" in logs_src
    derive_src = inspect.getsource(derive_module_synthesis_catalog)
    checks["derive_uses_facades"] = "FACADE_LAYERS" in derive_src
    checks["derive_uses_pair"] = "PAIR_EFFECT_SPECS" in derive_src
    checks["derive_uses_log"] = "LOG_FAMILY_SPECS" in derive_src
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    wired = {
        "derive": callable(derive_module_synthesis_catalog),
        "resolve": callable(resolve_synthesis_row),
        "install": callable(install_module_synthesis_finder),
        "catalog": bool(catalog),
        "impl": MODULE_SYNTHESIS_IMPL is True,
    }
    ok = all(checks.values()) and all(wired.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "action": "module_synthesis_plane_proof",
        "ok": ok,
        "checks": checks,
        "wired": wired,
        "wired_count": sum(1 for value in wired.values() if value),
        "catalog_count": len(catalog),
        "facade_count": kinds["facade"],
        "pair_count": kinds["pair_effect"],
        "log_count": kinds["log_family"],
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "module_synthesis_plane": True,
        "done_when_met": ok,
    }
    out = REPO_ROOT / "artifacts" / "capability-module-synthesis-plane"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "plane-report.json", report)
    return report
