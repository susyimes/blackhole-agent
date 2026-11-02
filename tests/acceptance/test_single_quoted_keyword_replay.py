"""Controller replay must keep a single-quoted pytest keyword as one argument.

Harvested login-audit validation used ``-k 'not builtin'``. cmd.exe treated
the quotes as characters, split on the space, and pytest exited 4 looking
for a file named ``builtin'``. The argument is rewritten to a cmd double
quoted token. The command stays on cmd.exe. An apostrophe that is already
inside double quotes is not rewritten, and a native exit 3 still surfaces.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def observe() -> tuple[bool, dict]:
    from blackhole_agent.unbound import powershell_replay_argv, replay_validation_command

    python = str(Path(sys.executable).resolve())
    quoted_python = f'"{python}"'
    with tempfile.TemporaryDirectory(prefix="bh-single-quote-") as directory:
        root = Path(directory)
        test_file = root / "test_sample.py"
        test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        keyword = (
            f"{quoted_python} -m pytest \"{test_file}\" -q -p no:cacheprovider "
            "--noconftest -k 'not builtin'"
        )
        percent = (
            f"{quoted_python} -c \"import sys; expected = chr(49)+chr(48)+chr(48)+chr(37); "
            "raise SystemExit(0 if len(sys.argv) > 1 and sys.argv[1] == expected else 1)\" "
            "'100%'"
        )
        apostrophe = (
            f"{quoted_python} -c \"import sys; raise SystemExit(0 if "
            "'not builtin' == 'not builtin' else 1)\""
        )
        native = (
            f"{quoted_python} -c \"import sys; raise SystemExit(3)\" 'extra words'"
        )
        keyword_result = replay_validation_command(root, keyword, timeout=60)
        percent_result = replay_validation_command(root, percent, timeout=30)
        apostrophe_result = replay_validation_command(root, apostrophe, timeout=30)
        native_result = replay_validation_command(root, native, timeout=30)
    observed = {
        "keyword_not_powershell": powershell_replay_argv(keyword) is None,
        "percent_not_powershell": powershell_replay_argv(percent) is None,
        "apostrophe_not_powershell": powershell_replay_argv(apostrophe) is None,
        "keyword_exit": keyword_result.get("reproduced_exit_code"),
        "keyword_stderr": (keyword_result.get("stderr_tail") or "")[-300:],
        "percent_exit": percent_result.get("reproduced_exit_code"),
        "apostrophe_exit": apostrophe_result.get("reproduced_exit_code"),
        "native_exit": native_result.get("reproduced_exit_code"),
    }
    passed = (
        observed["keyword_not_powershell"] is True
        and observed["percent_not_powershell"] is True
        and observed["apostrophe_not_powershell"] is True
        and observed["keyword_exit"] == 0
        and observed["percent_exit"] == 0
        and observed["apostrophe_exit"] == 0
        and observed["native_exit"] == 3
        and "builtin'" not in observed["keyword_stderr"]
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - probe must exit 0 with an unmet outcome
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
