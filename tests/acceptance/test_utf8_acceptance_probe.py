"""Behavior-acceptance children must print Hangul through a piped GBK code page.

The 2026-11-17 candidate crash was UnicodeEncodeError on U+D55C. Writing ASCII
bytes from one fixture does not keep the next probe alive.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

HANGUL = "\uD55C"


def _seed_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "blackhole@example.invalid"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "src").mkdir()
    (path / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    probe_dir = path / "tests" / "acceptance"
    probe_dir.mkdir(parents=True)
    # The child source stays ASCII. The Hangul exists only in the printed JSON.
    (probe_dir / "probe.py").write_text(
        "import json\n"
        "print(json.dumps({'passed': True, 'observed': '\\uD55C'}, ensure_ascii=False))\n",
        encoding="ascii",
    )
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=path, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def observe() -> tuple[bool, dict[str, object]]:
    from blackhole_agent.behavior_acceptance import replay_behavior_acceptance

    with tempfile.TemporaryDirectory(prefix="bh-utf8-probe-") as directory:
        root = Path(directory)
        baseline = _seed_repo(root)
        result = replay_behavior_acceptance(root, baseline, "tests/acceptance/probe.py", timeout=60)
    candidate = result.get("candidate") if isinstance(result.get("candidate"), dict) else {}
    stdout = str(candidate.get("stdout_tail") or "")
    error = str(result.get("error") or "")
    observed: dict[str, object] = {
        "exit_code": candidate.get("exit_code"),
        "hangul": HANGUL in stdout,
        "error": error[-240:],
    }
    passed = observed["exit_code"] == 0 and observed["hangul"] is True and "probe crashed" not in error
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
