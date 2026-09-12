"""Acceptance probe: the acceptance sweep adjudicates standalone probes.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_MET_PROBE = """import json
print(json.dumps({"passed": True, "observed": {"sentinel": "MET"}}))
"""

_UNMET_PROBE = """import json, sys
print(json.dumps({"passed": False, "observed": {"sentinel": "UNMET"}}))
sys.exit(0)
"""

_CRASHED_PROBE = """import sys
sys.stderr.write("boom")
sys.exit(3)
"""


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "acceptance-sweep"}
    try:
        from blackhole_agent.acceptance_sweep import iter_acceptance_probes, sweep_acceptance_probes
    except Exception as error:  # baseline source tree has no sweep runner
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="acceptance-sweep-probe-") as directory:
        repo = Path(directory)
        acceptance = repo / "tests" / "acceptance"
        acceptance.mkdir(parents=True)
        (acceptance / "test_met.py").write_text(_MET_PROBE, encoding="utf-8")
        (acceptance / "test_unmet.py").write_text(_UNMET_PROBE, encoding="utf-8")
        (acceptance / "test_crashed.py").write_text(_CRASHED_PROBE, encoding="utf-8")
        (acceptance / "helper.py").write_text("raise RuntimeError('must not be collected')\n", encoding="utf-8")

        discovered = [path.name for path in iter_acceptance_probes(repo)]
        report = sweep_acceptance_probes(repo, timeout=60)

    by_name = {Path(record["path"]).name: record for record in report["probes"]}
    met = by_name.get("test_met.py", {})
    unmet = by_name.get("test_unmet.py", {})
    crashed = by_name.get("test_crashed.py", {})
    checks = {
        "discovers_only_test_probes": discovered == ["test_crashed.py", "test_met.py", "test_unmet.py"],
        "met_probe_adjudicated": met.get("passed") is True and met.get("exit_code") == 0,
        "unmet_probe_adjudicated": unmet.get("passed") is False and unmet.get("exit_code") == 0,
        "crash_flagged_not_unmet": crashed.get("passed") is None and crashed.get("exit_code") == 3,
        "aggregate_counts": (
            report.get("total") == 3
            and report.get("met") == 1
            and report.get("unmet") == 1
            and report.get("crashed") == 1
        ),
        "crashed_probe_fails_sweep": report.get("ok") is False,
    }
    observed.update(
        {
            "checks": checks,
            "report": {key: report.get(key) for key in ("total", "met", "unmet", "crashed", "timed_out", "ok")},
            "sentinel": "BH-ACCEPTANCE-SWEEP-OK" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
