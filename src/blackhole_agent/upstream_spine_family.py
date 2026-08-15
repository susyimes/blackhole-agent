"""Spine-family engine: pair-effect and log-family share one catalog and load path.

Leftover host synthesizers (``_synthesize_effect_module`` /
``_synthesize_log_module``) were copies of the same create → populate →
``python -m`` contract. They now share one catalog and one populate.
A family is a :class:`SpineFamilyEngineRow`; shape (``pair`` / ``rows`` /
``state``) is data. Historical host synthesizer names stay as thin wrappers.

Apply, seal, and proof are owned here. Host ``run_pair_effect`` /
``_apply_log_family`` / ``seal_certificate`` / ``_seal_log_certificate``
names stay as thin wrappers. Shape-private cores (``_apply_pair_effect_core``,
``_seal_pair_certificate``, ``_seal_log_certificate_core``, apply_core_fn)
stay in the host token modules. A new family is a catalog row, not
another public engine copy.

No skill-route discovery.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
SPINE_FAMILY_ENGINE_IMPL = True
_SPINE_PREFIX = "blackhole_agent.upstream_total_spine_"

_LIVE_CATALOG: tuple["SpineFamilyEngineRow", ...] | None = None
_LIVE_INDEX: dict[str, "SpineFamilyEngineRow"] | None = None


@dataclass(frozen=True)
class SpineFamilyEngineRow:
    """One synthesizable spine family (log-shaped or pair-shaped)."""

    kind: str  # pair_effect | log_family
    name: str
    shape: str  # pair | rows | state
    populate: str  # signatures | exports
    fullname: str
    origin: str


def _pair_row(name: str) -> SpineFamilyEngineRow:
    return SpineFamilyEngineRow(
        kind="pair_effect",
        name=name,
        shape="pair",
        populate="signatures",
        fullname=f"{_SPINE_PREFIX}{name}",
        origin=f"<upstream-total-spine-effect:{name}>",
    )


def _log_row(name: str, *, shape: str = "rows") -> SpineFamilyEngineRow:
    return SpineFamilyEngineRow(
        kind="log_family",
        name=name,
        shape=shape,
        populate="exports",
        fullname=f"{_SPINE_PREFIX}{name}",
        origin=f"<upstream-total-spine-log:{name}>",
    )


def derive_spine_family_engine_catalog(
    *,
    extra_pair: Sequence[str] = (),
    extra_log: Sequence[str] = (),
    pair_families: Sequence[str] | None = None,
    log_families: Sequence[str] | None = None,
) -> tuple[SpineFamilyEngineRow, ...]:
    """Build the engine catalog from host spec registries plus optional probes."""

    log_shapes: dict[str, str] = {}
    if log_families is None:
        from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

        log_families = tuple(LOG_FAMILY_SPECS)
        log_shapes = {name: spec.shape for name, spec in LOG_FAMILY_SPECS.items()}
    if pair_families is None:
        from blackhole_agent.upstream_total_spine_effects import PAIR_EFFECT_SPECS

        pair_families = tuple(PAIR_EFFECT_SPECS)
    rows = [
        _log_row(name, shape=log_shapes.get(name, "rows"))
        for name in list(log_families) + list(extra_log)
    ]
    rows.extend(_pair_row(name) for name in list(pair_families) + list(extra_pair))
    return tuple(rows)


def spine_family_engine_catalog() -> tuple[SpineFamilyEngineRow, ...]:
    """Live catalog (cached). A probe extra does not mutate this."""

    global _LIVE_CATALOG, _LIVE_INDEX
    if _LIVE_CATALOG is None:
        _LIVE_CATALOG = derive_spine_family_engine_catalog()
        _LIVE_INDEX = {row.name: row for row in _LIVE_CATALOG}
    return _LIVE_CATALOG


def resolve_family_row(
    name: str,
    catalog: Sequence[SpineFamilyEngineRow] | None = None,
) -> SpineFamilyEngineRow | None:
    """Resolve one family name against the live catalog or a probe catalog."""

    if catalog is None:
        spine_family_engine_catalog()
        return (_LIVE_INDEX or {}).get(name)
    for row in catalog:
        if row.name == name:
            return row
    return None


def _impl_flag(name: str) -> str:
    return f"TOTAL_SPINE_{name.upper()}_IMPL"


def _populate_pair_effect(name: str, module: Any) -> None:
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        REPO_ROOT as EFFECTS_ROOT,
        SCHEMA_VERSION,
        StageRefused,
        TOTAL_SPINE_DEFAULT_ROOT,
        _effect_main,
        _forward,
        atomic_write_json,
        derive_pair_effect_signatures,
        durable_read_path,
        legacy_pipeline_was_used,
        pair_effect_public_names,
        utc_now_iso,
    )
    from pathlib import Path as _Path

    spec = PAIR_EFFECT_SPECS[name]
    module.__file__ = f"<upstream-total-spine-effect:{spec.effect}>"
    module.__doc__ = spec.summary
    g = module.__dict__
    import __future__
    import json as _json
    from typing import Any as _Any, Mapping as _Mapping, Sequence as _Sequence

    g["annotations"] = __future__.annotations
    g["json"] = _json
    g["Path"] = _Path
    g["Any"] = _Any
    g["Mapping"] = _Mapping
    g["Sequence"] = _Sequence
    g["atomic_write_json"] = atomic_write_json
    g["durable_read_path"] = durable_read_path
    g["legacy_pipeline_was_used"] = legacy_pipeline_was_used
    g["utc_now_iso"] = utc_now_iso
    g["SCHEMA_VERSION"] = SCHEMA_VERSION
    g["REPO_ROOT"] = EFFECTS_ROOT
    g["TOTAL_SPINE_DEFAULT_ROOT"] = TOTAL_SPINE_DEFAULT_ROOT
    g["StageRefused"] = StageRefused
    g[f"TOTAL_SPINE_{spec.upper}_IMPL"] = True
    g[f"TOTAL_SPINE_{spec.upper}_KIND"] = spec.kind
    g[f"TOTAL_SPINE_{spec.upper}_FILENAME"] = spec.filename
    g[f"TOTAL_SPINE_{spec.upper}_MIN_{spec.min_name}"] = spec.min_value
    g[f"TOTAL_SPINE_{spec.pred_upper}_KIND"] = spec.pred_kind

    public_functions = set(pair_effect_public_names(spec)) - {"main"}
    signatures = spec.signatures or derive_pair_effect_signatures(spec)
    filename = f"<upstream-total-spine-effect {spec.effect}>"
    for public_name, signature in signatures.items():
        if public_name == "main":
            stub = (
                "from __future__ import annotations\n"
                "from pathlib import Path\n"
                "from typing import Any, Mapping, Sequence\n"
                f"def main{signature}:\n"
                "    return _effect_main(_SPEC, argv)\n"
            )
            stub_ns = dict(g)
            stub_ns["_effect_main"] = _effect_main
            stub_ns["_SPEC"] = spec
            exec(compile(stub, filename, "exec"), stub_ns)
            g["main"] = stub_ns["main"]
            continue
        if public_name not in public_functions:
            continue
        stub = (
            "from __future__ import annotations\n"
            "from pathlib import Path\n"
            "from typing import Any, Mapping, Sequence\n"
            f"def {public_name}{signature}:\n"
            f"    return _forward(_SPEC, {public_name!r}, locals())\n"
        )
        stub_ns = dict(g)
        stub_ns["_forward"] = _forward
        stub_ns["_SPEC"] = spec
        exec(compile(stub, filename, "exec"), stub_ns)
        g[public_name] = stub_ns[public_name]


def _populate_log_family(name: str, module: Any) -> None:
    import json
    from pathlib import Path as _Path

    from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

    spec = LOG_FAMILY_SPECS[name]
    module.__file__ = f"<upstream-total-spine-log:{spec.name}>"
    module.__doc__ = spec.summary
    host = sys.modules["blackhole_agent.upstream_total_spine_logs"]
    g = module.__dict__
    import __future__

    g["annotations"] = __future__.annotations
    for export in spec.exports:
        if export == "annotations":
            continue
        if export == "json":
            g["json"] = json
            continue
        if export == "Path":
            g["Path"] = _Path
            continue
        if export == "main":
            g["main"] = getattr(host, spec.main_name)
            continue
        if hasattr(host, export):
            g[export] = getattr(host, export)


def populate_family_module(row: Any, module: Any) -> None:
    """Populate one synthesized family module from a catalog row."""

    kind = str(getattr(row, "kind", "") or "")
    name = str(getattr(row, "name", "") or "")
    if kind == "pair_effect":
        _populate_pair_effect(name, module)
        return
    if kind == "log_family":
        _populate_log_family(name, module)
        return
    raise KeyError(f"unknown family kind: {kind!r}")


def synthesize_family(kind: str, name: str) -> Any:
    """Materialize ``blackhole_agent.upstream_total_spine_<name>``."""

    row = resolve_family_row(name)
    if row is None or row.kind != kind:
        row = _pair_row(name) if kind == "pair_effect" else _log_row(name)
    module = sys.modules.get(row.fullname)
    if module is not None and module.__dict__.get(_impl_flag(name)):
        return module
    if module is None:
        module = types.ModuleType(row.fullname)
        sys.modules[row.fullname] = module
    populate_family_module(row, module)
    return module


def run_family_main(
    kind: str, name: str, module_globals: dict[str, Any]
) -> None:
    """``python -m`` entry: synthesize the namespace, then run its main."""

    module = synthesize_family(kind, name)
    for key, value in module.__dict__.items():
        if not (key.startswith("__") and key.endswith("__")):
            module_globals[key] = value
    if module_globals.get("__name__") == "__main__":
        sys.exit(module_globals["main"]())


def apply_spine_family(
    name: str, source: Any = None, **kwargs: Any
) -> dict[str, Any]:
    """Apply one catalog family. Public apply is this function, not a host copy."""

    row = resolve_family_row(name)
    if row is None:
        raise KeyError(f"unknown spine family: {name!r}")
    if row.kind == "log_family":
        from blackhole_agent.upstream_total_spine_logs import LOG_FAMILY_SPECS

        spec = LOG_FAMILY_SPECS[name]
        host = sys.modules["blackhole_agent.upstream_total_spine_logs"]
        core = getattr(host, spec.apply_core_fn)
        return core(source, **kwargs)
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        _apply_pair_effect_core,
    )

    return _apply_pair_effect_core(PAIR_EFFECT_SPECS[name], source, **kwargs)


def seal_spine_family(name: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one catalog family. Public seal is this function, not a host copy."""

    row = resolve_family_row(name)
    if row is None:
        raise KeyError(f"unknown spine family: {name!r}")
    if row.kind == "log_family":
        from blackhole_agent.upstream_total_spine_logs import (
            _seal_log_certificate_core,
        )

        return _seal_log_certificate_core(name, body)
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        _seal_pair_certificate,
    )

    return _seal_pair_certificate(PAIR_EFFECT_SPECS[name], body)


def run_spine_family(name: str, source: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Historical apply name: one catalog family."""

    return apply_spine_family(name, source, **kwargs)


def prove_spine_family(name: str) -> dict[str, Any]:
    """Prove one catalog family by name."""

    row = resolve_family_row(name)
    if row is None:
        raise KeyError(f"unknown spine family: {name!r}")
    if row.kind == "log_family":
        from blackhole_agent.upstream_total_spine_logs import _run_log_family_proof

        return _run_log_family_proof(name)
    from blackhole_agent.upstream_total_spine_effects import (
        PAIR_EFFECT_SPECS,
        _pair_effect_proof_core,
    )

    return _pair_effect_proof_core(PAIR_EFFECT_SPECS[name])


def builtin_spine_family_engine_proof() -> dict[str, Any]:
    """Hermetic proof: leftover pair/log synthesizers are one family engine."""

    import importlib
    import inspect

    checks: dict[str, bool] = {}
    catalog = spine_family_engine_catalog()
    kinds = {"pair_effect": 0, "log_family": 0}
    shapes = {"pair": 0, "rows": 0, "state": 0}
    for row in catalog:
        kinds[row.kind] = kinds.get(row.kind, 0) + 1
        shapes[row.shape] = shapes.get(row.shape, 0) + 1
    checks["impl"] = SPINE_FAMILY_ENGINE_IMPL is True
    checks["catalog_len"] = len(catalog) == 19
    checks["pair_count"] = kinds["pair_effect"] == 15
    checks["log_count"] = kinds["log_family"] == 4
    checks["pair_shape"] = shapes["pair"] == 15
    checks["rows_shape"] = shapes["rows"] == 3
    checks["state_shape"] = shapes["state"] == 1
    names = [row.name for row in catalog]
    checks["unique_names"] = len(names) == len(set(names))
    checks["resolve_solvency"] = (
        resolve_family_row("solvency") is not None
        and resolve_family_row("solvency").kind == "pair_effect"
    )
    checks["resolve_actuation"] = (
        resolve_family_row("actuation") is not None
        and resolve_family_row("actuation").kind == "log_family"
        and resolve_family_row("actuation").shape == "rows"
    )
    checks["resolve_execution"] = (
        resolve_family_row("execution") is not None
        and resolve_family_row("execution").shape == "state"
    )
    checks["unknown_refused"] = resolve_family_row("ratification") is None

    probe = derive_spine_family_engine_catalog(extra_pair=("ratification",))
    probe_row = resolve_family_row("ratification", catalog=probe)
    checks["probe_row"] = (
        probe_row is not None and probe_row.kind == "pair_effect"
    )
    checks["probe_not_live"] = resolve_family_row("ratification") is None
    checks["probe_len"] = len(probe) == len(catalog) + 1
    probe_log = derive_spine_family_engine_catalog(extra_log=("notation",))
    checks["probe_log"] = (
        resolve_family_row("notation", catalog=probe_log) is not None
        and resolve_family_row("notation", catalog=probe_log).kind == "log_family"
    )

    solvency = importlib.import_module("blackhole_agent.upstream_total_spine_solvency")
    actuation = importlib.import_module("blackhole_agent.upstream_total_spine_actuation")
    checks["solvency_runner"] = callable(
        getattr(solvency, "solvency_total_spine", None)
    )
    checks["actuation_runner"] = callable(
        getattr(actuation, "actuate_total_spine", None)
    )
    checks["run_dispatch"] = callable(run_spine_family)
    checks["apply_owned"] = callable(apply_spine_family)
    checks["seal_owned"] = callable(seal_spine_family)
    checks["prove_dispatch"] = callable(prove_spine_family)
    try:
        run_spine_family("not-a-family")
        checks["run_unknown_refused"] = False
    except KeyError:
        checks["run_unknown_refused"] = True
    try:
        seal_spine_family("not-a-family", {})
        checks["seal_unknown_refused"] = False
    except KeyError:
        checks["seal_unknown_refused"] = True

    effects_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_total_spine_effects.py"
    ).read_text(encoding="utf-8")
    logs_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_total_spine_logs.py"
    ).read_text(encoding="utf-8")
    synth_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_module_synthesis.py"
    ).read_text(encoding="utf-8")
    effects = importlib.import_module(
        "blackhole_agent.upstream_total_spine_effects"
    )
    logs = importlib.import_module("blackhole_agent.upstream_total_spine_logs")
    synth = importlib.import_module("blackhole_agent.upstream_module_synthesis")
    pair_synth = inspect.getsource(effects._synthesize_effect_module)
    log_synth = inspect.getsource(logs._synthesize_log_module)
    exec_src = inspect.getsource(synth._exec_row)
    pair_apply = inspect.getsource(effects.run_pair_effect)
    log_apply = inspect.getsource(logs._apply_log_family)
    pair_seal = inspect.getsource(effects.seal_certificate)
    log_seal = inspect.getsource(logs._seal_log_certificate)
    apply_src = inspect.getsource(apply_spine_family)
    seal_src = inspect.getsource(seal_spine_family)
    forward_src = inspect.getsource(effects._forward)
    checks["pair_synth_thin"] = "synthesize_family" in pair_synth
    checks["pair_synth_no_body"] = "pair_effect_public_names" not in pair_synth
    checks["log_synth_thin"] = "synthesize_family" in log_synth
    checks["log_synth_no_body"] = "spec.exports" not in log_synth
    checks["exec_uses_engine"] = "populate_family_module" in exec_src
    checks["exec_no_pair_import"] = "PAIR_EFFECT_SPECS" not in exec_src
    checks["exec_no_log_import"] = "LOG_FAMILY_SPECS" not in exec_src
    checks["pair_apply_thin"] = "apply_spine_family" in pair_apply
    checks["pair_apply_no_body"] = "_collect_preds" not in pair_apply
    checks["log_apply_thin"] = "apply_spine_family" in log_apply
    checks["log_apply_no_body"] = "apply_core_fn" not in log_apply
    checks["pair_seal_thin"] = "seal_spine_family" in pair_seal
    checks["pair_seal_no_body"] = "_certificate_material" not in pair_seal
    checks["log_seal_thin"] = "seal_spine_family" in log_seal
    checks["log_seal_no_body"] = "material_fn" not in log_seal
    checks["apply_no_host_public"] = (
        "run_pair_effect" not in apply_src and "_apply_log_family" not in apply_src
    )
    checks["seal_no_host_public"] = (
        "seal_certificate(" not in seal_src
        and "_seal_log_certificate(" not in seal_src
    )
    checks["forward_apply"] = "apply_spine_family" in forward_src
    checks["forward_seal"] = "seal_spine_family" in forward_src
    checks["forward_prove"] = "prove_spine_family" in forward_src
    checks["wrappers_stay"] = (
        "def _effect_main_from_module" in effects_src
        and "def _log_main_from_module" in logs_src
    )
    checks["synth_mentions_engine"] = "upstream_spine_family" in synth_src
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    wired = {
        "derive": callable(derive_spine_family_engine_catalog),
        "resolve": callable(resolve_family_row),
        "populate": callable(populate_family_module),
        "synthesize": callable(synthesize_family),
        "apply": callable(apply_spine_family),
        "seal": callable(seal_spine_family),
        "run": callable(run_spine_family),
        "impl": SPINE_FAMILY_ENGINE_IMPL is True,
    }
    ok = all(checks.values()) and all(wired.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "action": "spine_family_engine_proof",
        "ok": ok,
        "checks": checks,
        "wired": wired,
        "wired_count": sum(1 for value in wired.values() if value),
        "catalog_count": len(catalog),
        "pair_count": kinds["pair_effect"],
        "log_count": kinds["log_family"],
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "spine_family_engine": True,
        "done_when_met": ok,
    }
    out = REPO_ROOT / "artifacts" / "capability-spine-family-engine"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "plane-report.json", report)
    return report
