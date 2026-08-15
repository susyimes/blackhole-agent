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


# Synthesized modules (23 facade layers plus pair-effect and log-family
# total-spine families) resolve through one module-synthesis finder.
from blackhole_agent.upstream_module_synthesis import install_module_synthesis_finder

install_module_synthesis_finder()


__all__ = ["Kernel", "__version__", "package_dir"]
