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


__all__ = ["Kernel", "__version__", "package_dir"]
