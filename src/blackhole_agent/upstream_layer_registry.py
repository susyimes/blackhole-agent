"""Upstream facade layer registry: 23 thin modules collapse into data.

Every ``blackhole_agent.upstream_<layer>`` facade used to be a physical
17-line module whose entire body was ``export_layer_api(globals(), layer)``.
They are now synthesized on demand from :data:`FACADE_LAYERS` by a meta-path
finder installed from ``blackhole_agent/__init__.py``:

- ``import blackhole_agent.upstream_omniverse`` and
  ``from blackhole_agent import upstream_omniverse`` resolve through the
  finder and execute the same ``export_layer_api`` population the physical
  files performed;
- ``python -m blackhole_agent.upstream_<layer> --proof`` keeps working:
  the loader exposes ``get_code`` so ``runpy`` executes the bootstrap shim
  with ``__name__ == "__main__"``, and every ledger proof command keeps its
  historical spelling;
- behavior is unchanged by construction: the same function populates the
  same names for the same layer; the capability equivalence gate certifies
  the collapse with capture-before / verify-after snapshots.

No skill-route discovery.
"""

from __future__ import annotations

import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from typing import Any

FACADE_LAYERS: tuple[str, ...] = (
    "civilization",
    "commonwealth",
    "confederation",
    "continuum",
    "cosmos",
    "domain",
    "empire",
    "exacontinuum",
    "gigacontinuum",
    "hypercontinuum",
    "institution",
    "league",
    "megacontinuum",
    "multiverse",
    "omniverse",
    "petacontinuum",
    "quettacontinuum",
    "realm",
    "ronnacontinuum",
    "teracontinuum",
    "ultracontinuum",
    "yottacontinuum",
    "zettacontinuum",
)

_MODULE_PREFIX = "blackhole_agent.upstream_"


def bootstrap_layer(module_globals: dict[str, Any], layer_name: str) -> None:
    """Populate a synthesized facade module exactly like the physical files did.

    The physical files' namespace carried ``sys`` (imported for the
    ``__main__`` guard), ``export_layer_api`` (the imported populator), and
    ``annotations`` (the ``__future__`` import); the shim reproduces all
    three so the observable module surface is identical.
    """

    from blackhole_agent.upstream_stewardship_facade import export_layer_api

    export_layer_api(module_globals, layer_name)
    module_globals["export_layer_api"] = export_layer_api
    module_globals.pop("bootstrap_layer", None)
    if module_globals.get("__name__") == "__main__":
        sys.exit(module_globals["main"]())


def _layer_for(fullname: str) -> str | None:
    if not fullname.startswith(_MODULE_PREFIX):
        return None
    layer = fullname[len(_MODULE_PREFIX) :]
    return layer if layer in FACADE_LAYERS else None


class _FacadeLoader(Loader):
    """Executes the bootstrap shim for one synthesized facade module."""

    def __init__(self, fullname: str, layer: str) -> None:
        self._fullname = fullname
        self._layer = layer

    def _code(self) -> Any:
        source = (
            "from __future__ import annotations\n"
            "import sys\n"
            "from blackhole_agent.upstream_layer_registry import bootstrap_layer\n"
            f"bootstrap_layer(globals(), {self._layer!r})\n"
        )
        return compile(source, f"<upstream-layer {self._layer}>", "exec")

    def create_module(self, spec: ModuleSpec) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        exec(self._code(), module.__dict__)

    def get_code(self, fullname: str) -> Any:
        # runpy (`python -m blackhole_agent.upstream_<layer>`) requires this.
        return self._code()


class _FacadeFinder(MetaPathFinder):
    """Resolves ``blackhole_agent.upstream_<layer>`` for registered layers."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        layer = _layer_for(fullname)
        if layer is None:
            return None
        return ModuleSpec(
            fullname,
            _FacadeLoader(fullname, layer),
            origin=f"<upstream-layer:{layer}>",
            is_package=False,
        )


def install_facade_finder() -> None:
    """Idempotently install the facade meta-path finder."""

    if not any(isinstance(finder, _FacadeFinder) for finder in sys.meta_path):
        sys.meta_path.append(_FacadeFinder())
