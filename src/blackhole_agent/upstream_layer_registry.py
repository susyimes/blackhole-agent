"""Upstream facade layer registry: 23 thin modules collapse into data.

Every ``blackhole_agent.upstream_<layer>`` facade used to be a physical
17-line module whose entire body was ``export_layer_api(globals(), layer)``.
They are now synthesized on demand from :data:`FACADE_LAYERS` by the
shared module-synthesis finder installed from ``blackhole_agent/__init__.py``:

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


def install_facade_finder() -> None:
    """Historical name: install the shared module-synthesis finder."""

    from blackhole_agent.upstream_module_synthesis import (
        install_module_synthesis_finder,
    )

    install_module_synthesis_finder()
