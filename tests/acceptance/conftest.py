"""Standalone outcome probes are scripts, not pytest tests.

Each probe prints a JSON verdict and exits 0 for met and unmet outcomes so
the controller can replay the same file against baseline and candidate
source trees. Several legacy probes call ``sys.exit`` at module scope;
letting pytest import them aborts collection of the whole suite with an
INTERNALERROR. They are excluded from collection here and executed through
``blackhole_agent.acceptance_sweep`` instead.
"""

collect_ignore_glob = ["test_*.py"]
