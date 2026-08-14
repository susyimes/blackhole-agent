"""Blackhole Agent.

The project borrows mini-swe-agent's deliberately small controller style:
normalize inputs, keep a linear record of what happened, and make any mutation
explicit and reviewable.
"""

from pathlib import Path
from typing import Any, Protocol

__version__ = "0.1.0"

package_dir = Path(__file__).resolve().parent


class Kernel(Protocol):
    """Protocol for local execution kernels."""

    def run(self, task: str, *, cwd: Path, output_dir: Path, timeout_seconds: int = 3600) -> Any: ...


# The 23 thin ``upstream_<layer>`` facade modules are synthesized from the
# layer registry instead of living as physical files; install the finder so
# imports and ``python -m blackhole_agent.upstream_<layer>`` keep working.
from blackhole_agent.upstream_layer_registry import install_facade_finder

install_facade_finder()


__all__ = ["Kernel", "__version__", "package_dir"]
