"""Publication must refuse a protected-path diff that is not valid UTF-8.

Harvested loop stderr records UnicodeDecodeError in subprocess._readerthread
for byte 0xCE. A strict text-mode capture then returns stdout None while the
child exits 0, so the protected-path gate used to treat that listing as an
empty change set and allow the push. Prints JSON with boolean passed and
nonempty observed. Exit 0 for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _runner(script: Path, mode: str):
    def runner(command, **kwargs):
        return subprocess.run([sys.executable, str(script), mode], **kwargs)

    return runner


def observe() -> tuple[bool, dict]:
    from blackhole_agent.protected_paths import evaluate_candidate_protected_paths

    with tempfile.TemporaryDirectory(prefix="bh-protected-diff-") as directory:
        root = Path(directory)
        script = root / "emit_diff.py"
        script.write_text(
            "import sys\n"
            "mode = sys.argv[1]\n"
            "if mode == 'behavior':\n"
            "    data = b'src/blackhole_agent/unbound.py\\n'\n"
            "elif mode == 'protected':\n"
            "    data = b'src/blackhole_agent/supervisor.py\\n'\n"
            "else:\n"
            "    data = bytes([0xCE]) + b'src/blackhole_agent/supervisor.py\\n'\n"
            "sys.stdout.buffer.write(data)\n",
            encoding="ascii",
        )

        def verdict(mode: str):
            return evaluate_candidate_protected_paths(
                target_repo_path=root,
                candidate_repo_path=root,
                target_before="base",
                candidate_head="cand",
                command_runner=_runner(script, mode),
            )

        corrupt = verdict("corrupt")
        behavior = verdict("behavior")
        protected = verdict("protected")
    observed = {
        "corrupt_blocked": bool(corrupt.blocked),
        "corrupt_reason": corrupt.reason,
        "behavior_blocked": bool(behavior.blocked),
        "protected_blocked": bool(protected.blocked),
        "protected_touched": list(protected.touched),
    }
    passed = (
        observed["corrupt_blocked"] is True
        and "utf-8" in observed["corrupt_reason"].lower()
        and observed["behavior_blocked"] is False
        and observed["protected_blocked"] is True
        and "src/blackhole_agent/supervisor.py" in observed["protected_touched"]
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
