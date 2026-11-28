"""Find the release that changed an invoice using the scheduled report from a real Git repository."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

APPLICATION = """from pathlib import Path

def total(region):
    rate = int((Path(__file__).resolve().parents[1] / 'rates' / region).read_text())
    return 1250 + 1250 * rate // 100
"""
ORDER = """# replay-input: rates
import json, os
from invoice import total
cents = total({region!r})
if {region!r} == 'standard':
    with open(os.environ['BLACKHOLE_TEST_ORDER_LOG'], 'a', encoding='ascii') as stream:
        print(cents, file=stream)
print(json.dumps({{'passed': cents == 1350, 'observed': {{'cents': cents}}}}))
"""


def observe(scratch):
    from blackhole_agent.durable_state import durable_read_path
    from blackhole_agent.loop_acceptance_hygiene import HYGIENE_TASK_NAME, dispatch_acceptance_hygiene, schedule_acceptance_hygiene

    repo, output = scratch / "shop checkout", scratch / "nightly jobs & reports"
    repo.mkdir()
    timestamp = "2000-01-01T00:00:00Z"

    def git(*args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Shop", "-c", "user.email=shop@example.invalid",
             "-c", "commit.gpgSign=false", "-c", "core.hooksPath=.no-hooks", *args],
            cwd=repo, stderr=subprocess.PIPE, timeout=15,
            env={**os.environ, "GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp},
        )

    def commit(label):
        git("add", ".")
        git("commit", "-qm", label)
        return git("rev-parse", "HEAD").decode().strip()

    def local_state():
        return [git(*args) for args in (("rev-parse", "HEAD"), ("for-each-ref",), ("diff", "--cached"),
                                        ("diff",), ("status", "--porcelain", "-z", "--untracked-files=all"))]

    git("init", "-qb", "releases")
    probes = repo / "tests" / "acceptance"
    probes.mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src/invoice.py").write_text(APPLICATION, encoding="utf-8")
    rates = repo / "rates"
    rates.mkdir()
    for region in ("standard", "reduced", "local"):
        (rates / region).write_text("8")
        (probes / f"test_{region}.py").write_text(ORDER.format(region=region), encoding="utf-8")
    releases = [commit("open shop")]
    calls = []

    def scheduler(spec):
        calls.append(spec["name"])
        return {"backend": "fixture", "applied": True}

    scheduled = schedule_acceptance_hygiene(repo, output, scheduler=scheduler)
    first = dispatch_acceptance_hygiene(repo, output)
    for edition in range(1, 9):
        (repo / "edition").write_text(str(edition))
        if edition == 3:
            (rates / "reduced").write_text("temporarily unavailable")
        if edition == 4:
            git("switch", "-qc", "change-standard-rate")
            (rates / "standard").write_text("20")
            commit("change rate on topic branch")
            git("switch", "-q", "-")
            git("merge", "--no-ff", "-qm", "publish changed rate", "change-standard-rate")
            releases.append(git("rev-parse", "HEAD").decode().strip())
        else:
            if edition == 5:
                (rates / "reduced").write_text("20")
            releases.append(commit(f"publish catalog {edition}"))
    (rates / "local").write_text("12")
    git("add", "rates/local")
    (rates / "local").write_text("24")
    (repo / "draft.txt").write_text("operator's next catalog")
    before = local_state()
    task = ElementTree.parse(scheduled["task_xml_path"])
    executable = task.findtext(".//{*}Exec/{*}Command")
    arguments = task.findtext(".//{*}Exec/{*}Arguments")
    command = subprocess.list2cmdline([executable]) + " " + arguments if os.name == "nt" else scheduled["command"]
    order_log = Path(os.environ["BLACKHOLE_TEST_ORDER_LOG"])
    order_log.write_text("", encoding="ascii")
    launched = subprocess.run(command, cwd=scratch, capture_output=True, timeout=60)
    orders = order_log.read_text(encoding="ascii").splitlines()
    report = json.loads(durable_read_path(Path(first["report_path"])).read_text(encoding="utf-8"))
    origins = {row["name"]: row.get("history", {}) for row in report["regressions"]}
    totals = {Path(p["path"]).stem: p["observed"]["cents"] for p in report["probes"]}
    exact, gap, dirty = (origins.get("test_" + name, {}) for name in ("standard", "reduced", "local"))
    samples = exact.get("samples", {})
    checks = {
        "schedules_recurring_sweep": scheduled["scheduled"] and not scheduled["ran"] and calls == [HYGIENE_TASK_NAME],
        "green_pass_clean": first["ok"] and not first["regressions"],
        "registered_command": arguments == subprocess.list2cmdline(scheduled["command"][1:]) and launched.returncode == 1,
        "regression_surfaces_automatically": not report["ok"] and all(row["previously_green"] for row in report["regressions"]),
        "durable_report_names_regression": not report["ok"] and set(origins) == {"test_local", "test_reduced", "test_standard"},
        "live_invoices": first["ok"] and totals == {"test_standard": 1500, "test_reduced": 1500, "test_local": 1550},
        "exact_release": exact.get("first_bad") == releases[4] and exact.get("last_good") == releases[3],
        "replayed_totals": [samples.get(releases[i], {}).get("observed") for i in (3, 4)] == [
            {"cents": 1350}, {"cents": 1500}],
        "binary_search": orders[:1] == ["1500"] and len(orders) == 1 + len(samples) and 0 < len(samples) <= 5,
        "untestable_interval": gap.get("candidates") == releases[3:6] and gap.get("first_bad") is None
        and all(gap.get("samples", {}).get(sha, {}).get("error") for sha in releases[3:5]),
        "checkout_only": dirty.get("status") == "bad_endpoint_passed" and dirty.get("first_bad") is None
        and dirty.get("samples", {}).get(releases[-1], {}).get("observed") == {"cents": 1350},
        "operator_edits_preserved": local_state() == before and (repo / "draft.txt").read_text() == "operator's next catalog",
    }
    for path in rates.iterdir():
        path.write_text("8")
    recovered = dispatch_acceptance_hygiene(repo, Path(scheduled["hygiene_dir"]))
    checks["recovery_clears_regression"] = recovered["ran"] and recovered["ok"] and not recovered["regressions"]
    observed = {"totals": totals, "checks": checks, "expected_first_bad": releases[4],
                "reported_first_bad": exact.get("first_bad"), "possible_commits": gap.get("candidates", []),
                "standard_orders_in_execution_order": orders, "dirty_status": dirty.get("status"),
                "launcher_exit": launched.returncode,
                "family": "acceptance-sweep-hygiene", "regressions": sorted(origins),
                "sentinel": "BH-ACCEPTANCE-HYGIENE-OK" if all(checks.values()) else ""}
    return {"passed": all(checks.values()), "observed": observed}


if __name__ == "__main__":
    try:
        with tempfile.TemporaryDirectory(prefix="invoice-history-") as tmp:
            with patch.dict(os.environ, BLACKHOLE_TEST_ORDER_LOG=str(Path(tmp) / "observed orders")):
                result = observe(Path(tmp))
    except Exception as exc:
        result = {"passed": False, "observed": {"error": str(exc)}}
    print(json.dumps(result))
