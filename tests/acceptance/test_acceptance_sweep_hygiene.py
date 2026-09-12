"""Acceptance probe: scheduled hygiene surfaces probe-contract regressions.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_MET = """import json
print(json.dumps({"passed": True, "observed": {"sentinel": "GREEN"}}))
"""

_BROKEN = """import json
print(json.dumps({"passed": False, "observed": {"sentinel": "BROKEN"}}))
"""


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "acceptance-sweep-hygiene"}
    try:
        from blackhole_agent.durable_state import durable_read_path
        from blackhole_agent.loop_acceptance_hygiene import (
            HYGIENE_TASK_NAME,
            dispatch_acceptance_hygiene,
            hygiene_report_path,
            schedule_acceptance_hygiene,
        )
    except Exception as error:  # baseline source tree has no hygiene wiring
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="acceptance-hygiene-probe-") as directory:
        repo = Path(directory) / "repo"
        acceptance = repo / "tests" / "acceptance"
        acceptance.mkdir(parents=True)
        (acceptance / "test_stable.py").write_text(_MET, encoding="utf-8")
        flaky = acceptance / "test_flaky.py"
        flaky.write_text(_MET, encoding="utf-8")

        applied: list[str] = []

        def scheduler(registration: dict) -> dict:
            applied.append(str(registration.get("name") or ""))
            return {"backend": "proof", "applied": True}

        scheduled = schedule_acceptance_hygiene(repo, scheduler=scheduler)
        green = dispatch_acceptance_hygiene(repo)
        flaky.write_text(_BROKEN, encoding="utf-8")
        broken = dispatch_acceptance_hygiene(repo)
        report = json.loads(durable_read_path(hygiene_report_path(repo)).read_text(encoding="utf-8"))
        flaky.write_text(_MET, encoding="utf-8")
        recovered = dispatch_acceptance_hygiene(repo)

    checks = {
        "schedules_recurring_sweep": scheduled.get("scheduled") is True
        and scheduled.get("ran") is False
        and applied == [HYGIENE_TASK_NAME],
        "green_pass_clean": green.get("ok") is True and green.get("regressions") == [],
        "regression_surfaces_automatically": broken.get("ok") is False
        and [item.get("name") for item in broken.get("regressions") or []] == ["test_flaky"],
        "durable_report_names_regression": report.get("ok") is False
        and [item.get("name") for item in report.get("regressions") or []] == ["test_flaky"],
        "recovery_clears_regression": recovered.get("ok") is True and recovered.get("regressions") == [],
    }
    observed.update(
        {
            "checks": checks,
            "regressions": [item.get("name") for item in broken.get("regressions") or []],
            "sentinel": "BH-ACCEPTANCE-HYGIENE-OK" if all(checks.values()) else "",
        }
    )
    return {"passed": bool(all(checks.values())), "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
